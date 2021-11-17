#!/usr/bin/env python
import sys
import os
import time
import re
from multiprocessing import Process, Manager, Value
import optparse
import runpy
import pyinstrument
from pyinstrument import Profiler, renderers
from pyinstrument.session import Session
import pyinstrument_flame
import psutil
import pynvml
import drawSvg as draw
import svg_stack as ss


def create_svg(svg_name, info, label1, label2, WIDTH=1200, HEIGHT=200):
    d_cpu = draw.Drawing(WIDTH, HEIGHT, displayInline=False)

    x_offset = WIDTH * 0.009
    x_scale = (WIDTH - 2 * x_offset) / info[-1][0]
    y_scale = HEIGHT / 200
    cpu_max = max([item[1] for item in info])
    mem_max = max([item[2] for item in info])
    for i in range(1, len(info)):
        prev = info[i - 1]
        line = info[i]
        x0 = x_scale * prev[0] + x_offset
        x1 = x_scale * line[0] + x_offset
        # CPU
        y = 0.475 * HEIGHT / cpu_max * prev[1]
        y_offset = HEIGHT / 2
        r = draw.Rectangle(x0, 0 + y_offset, x1 - x0, y, fill='#83e4eb')
        r.appendTitle(f'{label1}: {prev[1]:.1f}')
        d_cpu.append(r)
        # MEM
        y_offset = HEIGHT
        y = 0.475 * HEIGHT / mem_max * prev[2]
        r = draw.Rectangle(x0, 0, x1 - x0, y, fill='#33ffc4')
        r.appendTitle(f'{label2}: {prev[2]:.1f}') 
        d_cpu.append(r)
        
    d_cpu.append(draw.Rectangle(x_scale * info[0][0] + x_offset, 0 + HEIGHT/2, WIDTH - 2*x_offset, 1, fill='#83e4eb'))
    d_cpu.append(draw.Text(label1 + f' (Max = {cpu_max:.1f}%)', 32, x_offset, HEIGHT/2 + 30, fill='white'))
    d_cpu.append(draw.Rectangle(x_scale * info[0][0] + x_offset, 0, WIDTH - 2*x_offset, 1, fill='#33ffc4'))
    d_cpu.append(draw.Text(label2 + f' (Max = {mem_max:.1f}%)', 32, x_offset, 0 + 30, fill='white'))

    d_cpu.saveSvg(svg_name)


class SysInfo:
    def __init__(self, output, flag, interval=1):
        self.output = output
        self.flag = flag
        self.interval = interval
        self.info = []
        self.info_gpu = []
    
    def start(self):
        try:
            pynvml.nvmlInit()
            gpu_handle =  pynvml.nvmlDeviceGetHandleByIndex(0)
            has_gpu = pynvml.nvmlDeviceGetCount() > 0
        except:
            has_gpu = False

        start = time.time()
        while self.flag.value:
            now = time.time() - start
            self.info.append((now, psutil.cpu_percent(), psutil.virtual_memory().percent))
            if has_gpu:
                gpu_handle =  pynvml.nvmlDeviceGetHandleByIndex(0)
                gpu = pynvml.nvmlDeviceGetUtilizationRates(gpu_handle)
                mem = pynvml.nvmlDeviceGetMemoryInfo(gpu_handle)
                mem = 100 * mem.used / mem.total
                self.info_gpu.append((now, gpu.gpu, mem))
            # TODO: adjust sleep duration based on actual timing
            time.sleep(self.interval)

        create_svg(self.output + '_cpu.svg', self.info, '% CPU', '% RAM')
        if has_gpu:
            create_svg(self.output + '_gpu.svg', self.info_gpu, '% GPU', '% G-RAM')


def main():
    usage = f'usage: python {sys.argv[0]} [options] scriptfile [arg] ...'
    parser = optparse.OptionParser(usage=usage, version='0.1')
    parser.allow_interspersed_args = False

    parser.add_option(
        '-o',
        '--output',
        dest='output',
        action='store',
        type='string',
        help='output file name without extension (default: perf_output)',
        default='perf_output',
    )

    parser.add_option(
        '-p',
        '--prof_interval',
        dest='prof_interval',
        action='store',
        type='float',
        help='profiler sampling interval (default: 100 samples/seconcd)',
        default='0.01',
    )

    parser.add_option(
        '-s',
        '--sys_interval',
        dest='sys_interval',
        action='store',
        type='float',
        help='system activity sampling interval (default: 1 sample/seconcd)',
        default='1',
    )   

    options, args = parser.parse_args()
    if not args:
        print(usage)
        return
    
    print('=' * 40)
    print('Script file to profile:', args)
    print(f'Profiling output: {options.output}[.svg/.html]')
    print('Profiler sampling frequency:', int(1/options.prof_interval), 'Hz')
    print('System activity sampling frequency:', int(1/options.sys_interval), 'Hz')
    try:
        pynvml.nvmlInit()
        print('Number of GPUs:', pynvml.nvmlDeviceGetCount())
    except:
        print('No GPU found')
    print('=' * 40)

    progname = args[0]
    outname = options.output

    flag = Value('b', 1)
    info = SysInfo(output=outname, flag=flag, interval=options.sys_interval)
    p = Process(target=info.start, args=())
    p.start()

    # profile
    sys.path.insert(0, os.path.dirname(progname))

    code = "run_path(progname, run_name='__main__')"
    globs = {"run_path": runpy.run_path, "progname": progname}

    profiler = Profiler(interval=options.prof_interval, async_mode='disabled')

    profiler.start()

    sys.argv = args
    try:
        exec(code, globs, None)
    except (SystemExit, KeyboardInterrupt):
        pass

    session = profiler.stop()

    renderer = renderers.HTMLRenderer(show_all=True, timeline=True)
    with open(outname + '.html', 'w') as f:
        f.write(renderer.render(session))

    renderer = pyinstrument_flame.FlameGraphRenderer(title=progname, flamechart=True)
    with open(outname + '_cs.svg', 'w') as f:
        f.write(renderer.render(session))

    flag.value = 0

    p.join()

    doc = ss.Document()
    layout = ss.VBoxLayout()
    layout.setSpacing(5)

    layout.addSVG(outname + '_cs.svg')
    layout.addSVG(outname + '_cpu.svg')
    if os.path.exists(outname + '_gpu.svg'):
        layout.addSVG(outname + '_gpu.svg')

    doc.setLayout(layout)
    doc.save(outname + '.svg')


if __name__ == '__main__':
    main()
