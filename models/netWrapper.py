import numpy as np
import torch
from models.metrics import *
import time
from datetime import timedelta
import torch
import pandas as pd


# def format_time(avg_time):
#     avg_time = timedelta(seconds=avg_time)
#     total_seconds = int(avg_time.total_seconds())
#     hours, remainder = divmod(total_seconds, 3600)
#     minutes, seconds = divmod(remainder, 60)
#     return f"{hours:02d}:{minutes:02d}:{int(seconds):02d}.{str(avg_time.microseconds)[:3]}"


class NetWrapper:
    def __init__(self, model, loss_function, device='cpu', classification=True, metric_type="auc"):
        self.model = model
        self.loss_fun = loss_function
        self.device = torch.device(device)
        self.classification = classification  # 分类任务
        self.metric_type = metric_type

    def train_test_one_fold(self, train_loader, test_loader,optimizer, max_epochs=3,  scheduler=None, clipping=None,
                            early_stopping=None, logger=None, log_every=1):

        for i in range(max_epochs):
            begin = time.time()
            metric, loss = self.train_one_epoch(
                train_loader, optimizer, clipping=None)
            end = time.time()
            duration = end - begin
            if i % log_every == 0:
                msg = f'[TRAIN] Epoch: {i+1}, metric: {self.metric_type}, TR loss: {loss} TR metric: {metric}'
                print(msg)
                print(
                    f"- Elapsed time: {str(duration)[:4]}s , Time estimation in a fold:{str(duration*max_epochs/60)[:4]}min")
            # r 可能要加early_stop

        metric, loss = self.test(test_loader)
        msg = f'[TEST] metric: {self.metric_type}, TS loss: {loss} TS metric: {metric}'
        print(msg)
        return metric, loss

    def train_one_epoch(self, train_loader, optimizer, clipping=None):  # y 每个epoch的训练
        model = self.model.to(self.device)
        model.train()  # 训练模式

        loss_all = 0
        acc_all = 0
        # y_preds = np.array([])
        # y_labels = np.array([])
        y_preds = []
        y_labels = []
        for batch in train_loader: #或者统一labels形式
            # graph: Batch(batch=[782], edge_attr=[845, 14], edge_index=[2, 1690], x=[782, 186], y=[32])
            # print(a)
            labels = batch.y
            feats = batch
            feats = feats.to(self.device)
            optimizer.zero_grad()
            output = model(feats)

            if not isinstance(output, tuple):
                output = (output,)

            # y_labels = np.concatenate((y_labels, data.y.data.cpu().view(-1).numpy()), axis=0)
            # y_preds = np.concatenate((y_preds, output[0].data[:,1].cpu().view(-1).numpy()), axis=0)
            y_labels += list(labels.detach().numpy())
            y_preds += list(output[0].detach().numpy()[:, 1])

            if self.classification:
                loss, acc = self.loss_fun(labels, *output)
                loss.backward()
                try:
                    num_graphs = feats.num_graphs
                except TypeError:
                    num_graphs = feats.adj.size(0)
                loss_all += loss.item() * num_graphs
                acc_all += acc.item() * num_graphs
            else:
                loss = self.loss_fun(labels, *output)
                loss.backward()
                loss_all += loss.item()

            if clipping is not None:  # Clip gradient before updating weights
                torch.nn.utils.clip_grad_norm_(model.parameters(), clipping)
            optimizer.step()

        if self.classification:
            return get_metric(y_labels, y_preds, self.metric_type), loss_all / len(train_loader.dataset)
        else: # mse
            return get_metric(y_labels, y_preds, self.metric_type), loss_all / len(train_loader.dataset)

    def test(self, test_loader):
        model = self.model.to(self.device)
        model.eval()

        loss_all = 0
        acc_all = 0

        y_preds = []
        y_labels = []

        for data in test_loader:
            data = data.to(self.device)
            output = model(data)

            if not isinstance(output, tuple):
                output = (output,)

            y_labels += list(data.y.detach().numpy())
            y_preds += list(output[0].detach().numpy()[:, 1])

            if self.classification:
                loss, acc = self.loss_fun(data.y, *output)

                try:
                    num_graphs = data.num_graphs
                except TypeError:
                    num_graphs = data.adj.size(0)

                loss_all += loss.item() * num_graphs
                acc_all += acc.item() * num_graphs
            else:
                loss = self.loss_fun(data.y, *output)
                loss_all += loss.item()

        if self.classification:
            return get_metric(y_labels, y_preds, self.metric_type), loss_all / len(test_loader.dataset)
        else: # mse
            return get_metric(y_labels, y_preds, self.metric_type), loss_all / len(test_loader.dataset)
