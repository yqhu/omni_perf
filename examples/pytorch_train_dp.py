import os
import sys
import torch
import torch.nn as nn
import torch.optim as optim


device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

class ToyModel(nn.Module):
    def __init__(self):
        super(ToyModel, self).__init__()
        self.net1 = nn.Linear(1000, 10000)
        self.relu = nn.ReLU()
        self.net2 = nn.Linear(10000, 5)

    def forward(self, x):
        return self.net2(self.relu(self.net1(x)))


def train():
    model = ToyModel()
    dp_model = torch.nn.DataParallel(model).to(device)

    loss_fn = nn.MSELoss()
    optimizer = optim.SGD(dp_model.parameters(), lr=0.001)

    for epoch in range(20):
        optimizer.zero_grad()
        outputs = dp_model(torch.randn(8000, 1000).to(device))
        labels = torch.randn(8000, 5).to(device)

        loss_fn(outputs, labels).backward()
        optimizer.step()


if __name__ == '__main__':
    train()