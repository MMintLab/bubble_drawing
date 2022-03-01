import numpy as np
import os
import torch
import torch.nn as nn
import torch.nn.functional as F
import pytorch_lightning as pl
import abc

from bubble_control.bubble_learning.models.bubble_autoencoder import BubbleAutoEncoderModel
from bubble_control.bubble_learning.models.aux.fc_module import FCModule


class ICPApproximationModel(pl.LightningModule):

    def __init__(self, input_sizes, num_fcs=2, fc_h_dim=100,
                 skip_layers=None, lr=1e-4, dataset_params=None, activation='relu', load_autoencoder_version=0, num_imprints_to_log=40):
        super().__init__()
        self.input_sizes = input_sizes
        self.num_fcs = num_fcs
        self.fc_h_dim = fc_h_dim
        self.skip_layers = skip_layers
        self.lr = lr
        self.dataset_params = dataset_params
        self.activation = activation
        self.mse_loss = nn.MSELoss()
        self.num_imprints_to_log = num_imprints_to_log
        self.autoencoder = self._load_autoencoder(load_version=load_autoencoder_version,
                                                  data_path=self.dataset_params['data_name'])
        self.autoencoder.freeze()
        self.img_embedding_size = self.autoencoder.img_embedding_size  # load it from the autoencoder
        self.pose_estimation_network = self._get_pose_estimation_network()
        self.save_hyperparameters()  # Important! Every model extension must add this line!

    @classmethod
    def get_name(cls):
        return 'icp_approximation_model'

    @property
    def name(self):
        return self.get_name()

    def _get_pose_estimation_network(self):
        input_size = self.img_embedding_size
        output_size = self.input_sizes['object_pose']
        pen_sizes = [input_size] + [self.fc_h_dim]*self.num_fcs + [output_size]
        pen = FCModule(sizes=pen_sizes, skip_layers=self.skip_layers, activation=self.activation)
        return pen

    def forward(self, imprint):
        img_embedding = self.autoencoder.encode(imprint)
        predicted_pose = self.pose_estimation_network(img_embedding)
        return predicted_pose

    def _step(self, batch, batch_idx, phase='train'):

        model_input = self.get_model_input(batch)
        ground_truth = self.get_model_output(batch)

        model_output = self.forward(*model_input)

        loss = self._compute_loss(model_output, *ground_truth)

        # Log the results: -------------------------
        self.log('{}_batch'.format(phase), batch_idx)
        self.log('{}_loss'.format(phase), loss)
        # TODO: Log poses
        return loss

    def _get_sizes(self):
        sizes = {}
        sizes.update(self.input_sizes)
        sizes['dyn_input_size'] = self._get_dyn_input_size(sizes)
        sizes['dyn_output_size'] = self._get_dyn_output_size(sizes)
        return sizes

    def get_input_keys(self):
        input_keys = ['imprint']
        return input_keys

    @abc.abstractmethod
    def get_model_output_keys(self):
        output_keys = ['object_pose']
        return output_keys

    def training_step(self, train_batch, batch_idx):
        loss = self._step(train_batch, batch_idx, phase='train')
        return loss

    def validation_step(self, val_batch, batch_idx):
        loss = self._step(val_batch, batch_idx, phase='val')
        return loss

    def configure_optimizers(self):
        optimizer = torch.optim.Adam(self.parameters(), lr=self.lr)
        return optimizer

    def get_model_input(self, sample):
        input_key = self.get_input_keys()
        model_input = [sample[key] for key in input_key]
        model_input = tuple(model_input)
        return model_input

    def get_model_output(self, sample):
        output_keys = self.get_model_output_keys()
        model_output = [sample[key] for key in output_keys]
        model_output = tuple(model_output)
        return model_output

    def _compute_loss(self, obj_pose_pred, obj_pose_gth):
        # MSE Loss on position and orientation (encoded as aixis-angle 3 values)
        # axis_angle_pred = obj_pose_pred[..., 3:]
        # R_pred = batched_trs.axis_angle_to_matrix(axis_angle_pred)
        # t_pred = obj_pose_pred[..., :3]
        # axis_angle_gth = obj_pose_gth[..., 3:]
        # R_gth = batched_trs.axis_angle_to_matrix(axis_angle_gth)
        # t_gth = obj_pose_gth[..., :3]
        # pose_loss = self.pose_loss(R_1=R_pred, t_1=t_pred, R_2=R_gth, t_2=t_gth, model_points=object_model)
        # TODO: consider using 'marker' object model and use pose_loss
        pose_loss = self.mse_loss(obj_pose_pred, obj_pose_gth)
        loss = pose_loss
        return loss


    # AUX FUCTIONS -----------------------------------------------------------------------------------------------------

    def _load_autoencoder(self, load_version, data_path, load_epoch=None, load_step=None):
        Model = BubbleAutoEncoderModel
        model_name = Model.get_name()
        if load_epoch is None or load_step is None:
            version_chkp_path = os.path.join(data_path, 'tb_logs', '{}'.format(model_name),
                                             'version_{}'.format(load_version), 'checkpoints')
            checkpoints_fs = [f for f in os.listdir(version_chkp_path) if
                              os.path.isfile(os.path.join(version_chkp_path, f))]
            checkpoint_path = os.path.join(version_chkp_path, checkpoints_fs[0])
        else:
            checkpoint_path = os.path.join(data_path, 'tb_logs', '{}'.format(model_name),
                                           'version_{}'.format(load_version), 'checkpoints',
                                           'epoch={}-step={}.ckpt'.format(load_epoch, load_step))

        model = Model.load_from_checkpoint(checkpoint_path)

        return model


class FakeICPApproximationModel(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, imprint):
        fake_pose_shape = imprint.shape[:-3] + (6,)
        fake_pose = torch.zeros(fake_pose_shape, device=imprint.device, dtype=imprint.dtype) # encoded as axis-angle
        return fake_pose

    @classmethod
    def get_name(cls):
        return 'fake_icp_approximation_model'

    @property
    def name(self):
        return self.get_name()

