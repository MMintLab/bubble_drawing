import torch
import torch.nn as nn
import torch.nn.functional as F
import pytorch_lightning as pl
import matplotlib.pyplot as plt
from matplotlib import cm
import torchvision
import numpy as np
import os
import sys

from bubble_control.bubble_learning.models.aux.fc_module import FCModule
from bubble_control.bubble_learning.models.aux.img_encoder import ImageEncoder
from bubble_control.bubble_learning.models.aux.img_decoder import ImageDecoder
from bubble_control.bubble_learning.models.bubble_autoencoder import BubbleAutoEncoderModel
from bubble_control.bubble_learning.models.dynamics_model_base import DynamicsModelBase


class ObjectPoseDynamicsModel(DynamicsModelBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dyn_model = self._get_dyn_model()
        self.save_hyperparameters()

    @classmethod
    def get_name(cls):
        return 'object_pose_dynamics_model'

    def _get_img_encoder(self):
        sizes = self._get_sizes()
        img_size = sizes['imprint']# (C_in, W_in, H_in)
        img_encoder = ImageEncoder(input_size=img_size,
                                   latent_size=self.img_embedding_size,
                                   num_convs=self.encoder_num_convs,
                                   conv_h_sizes=self.encoder_conv_hidden_sizes,
                                   ks=self.ks,
                                   num_fcs=self.num_encoder_fcs,
                                   fc_hidden_size=self.fc_h_dim,
                                   activation=self.activation)
        return img_encoder

    def _get_dyn_input_size(self, sizes):
        dyn_input_size = sizes['init_object_pose'] + sizes['init_pos'] + sizes['init_quat'] + self.object_embedding_size + sizes['action']
        return dyn_input_size

    def _get_dyn_output_size(self, sizes):
        dyn_output_size = sizes['init_object_pose']
        return dyn_output_size

    def forward(self, obj_pose, pos, ori, object_model, action):
        # sizes = self._get_sizes()
        # obj_pos_size = sizes['object_position']
        # obj_quat_size = sizes['object_orientation']
        # obj_pose_size = obj_pos_size + obj_quat_size
        obj_model_emb = self.object_embedding_module(object_model)  # (B, imprint_emb_size)
        dyn_input = torch.cat([obj_pose, pos, ori, obj_model_emb, action], dim=-1)
        dyn_output = self.dyn_model(dyn_input)
        obj_pose_next = dyn_output # we only predict object_pose
        return obj_pose_next

    def get_state_keys(self):
        state_keys = ['init_object_pose', 'init_pos', 'init_quat', 'object_model']
        return state_keys
    
    def get_input_keys(self):
        input_keys = ['init_object_pose', 'init_pos', 'init_quat', 'object_model']
        return input_keys

    def get_model_output_keys(self):
        output_keys = ['init_object_pose']
        return output_keys

    def get_next_state_map(self):
        next_state_map = {
            'init_object_pose': 'final_object_pose'
        }
        return next_state_map

    def _compute_loss(self, obj_pose_pred, obj_pose_gth):
        # MSE Loss on position and orientation (encoded as aixis-angle 3 values)
        pose_loss = self.mse_loss(obj_pose_pred, obj_pose_gth)
        loss = pose_loss
        return loss