#!/usr/bin/env python
import sys
import os
import time
import re
from multiprocessing import Process, Manager, Value
import argparse
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
    for i in range(1, len(info)):
        prev = info[i - 1]
        line = info[i]
        x0 = x_scale * prev[0] + x_offset
        x1 = x_scale * line[0] + x_offset
        # CPU
        y = y_scale * prev[1]
        y_offset = HEIGHT / 2
        r = draw.Rectangle(x0, 0 + y_offset, x1 - x0, y, fill='#83e4eb')
        r.appendTitle(f'{label1}: {prev[1]:.1f}')
        d_cpu.append(r)
        # MEM
        y_offset = HEIGHT
        y = y_scale * prev[2] * 1
        r = draw.Rectangle(x0, 0, x1 - x0, y, fill='#33ffc4')
        r.appendTitle(f'{label2}: {prev[2]:.1f}') 
        d_cpu.append(r)
        
    d_cpu.append(draw.Rectangle(x_scale * info[0][0] + x_offset, 0 + HEIGHT/2, WIDTH - 2*x_offset, 1, fill='#83e4eb'))
    d_cpu.append(draw.Text(label1, 24, x_offset, HEIGHT/2 + 20, fill='white'))
    d_cpu.append(draw.Rectangle(x_scale * info[0][0] + x_offset, 0, WIDTH - 2*x_offset, 1, fill='#33ffc4'))
    d_cpu.append(draw.Text(label2, 24, x_offset, 0 + 20, fill='white'))

    d_cpu.saveSvg(svg_name)


class SysInfo:
    def __init__(self, output, flag, interval=1):
        self.output = output
        self.flag = flag
        self.interval = interval
        self.info = []
        self.info_gpu = []
    
    def start(self):
        pynvml.nvmlInit()
        gpu_handle =  pynvml.nvmlDeviceGetHandleByIndex(0)
        has_gpu = pynvml.nvmlDeviceGetCount() > 0

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
    parser = argparse.ArgumentParser()
    parser.add_argument('script', help='python script to profile')
    parser.add_argument('-o', '--output', type=str, default='perf_output', help='output file name without extension (default: perf_output)')
    parser.add_argument('--prof_interval', type=float, default=0.001, help='profiler sampling interval (default: 1000 samples/seconcd)')
    parser.add_argument('--sys_interval', type=float, default=1, help='system activity sampling interval (default: 1 sample/seconcd)')
    args = parser.parse_args()
    print('=' * 40)
    print('Script to profile:', args.script)
    print(f'Profiling output: {args.output}[.svg/.html]')
    print('Profiler sampling frequency:', int(1/args.prof_interval), 'Hz')
    print('System activity sampling frequency:', int(1/args.sys_interval), 'Hz')
    pynvml.nvmlInit()
    print('Number of GPUs:', pynvml.nvmlDeviceGetCount())
    print('=' * 40)

    progname = args.script
    outname = args.output

    flag = Value('b', 1)
    info = SysInfo(output=outname, flag=flag, interval=args.sys_interval)
    p = Process(target=info.start, args=())
    p.start()

    # profile
    sys.path.insert(0, os.path.dirname(progname))

    code = "run_path(progname, run_name='__main__')"
    globs = {"run_path": runpy.run_path, "progname": progname}

    profiler = Profiler(interval=args.prof_interval, async_mode='disabled')

    profiler.start()

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
    layout.setSpacing(10)

    layout.addSVG(outname + '_cs.svg')
    layout.addSVG(outname + '_cpu.svg')
    if os.path.exists(outname + '_gpu.svg'):
        layout.addSVG(outname + '_gpu.svg')

    doc.setLayout(layout)
    doc.save(outname + '.svg')


if __name__ == '__main__':
    main()
