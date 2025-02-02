import os
import torch
import warnings
import torchvision.models as models
from models import TernausNet, unet, checkpointed_unet, inception, coordconv
from utils.utils import chop_layer, get_key_def


def load_checkpoint(filename):
    ''' Loads checkpoint from provided path
    :param filename: path to checkpoint as .pth.tar or .pth
    :return: (dict) checkpoint ready to be loaded into model instance 
    '''
    try:
        print("=> loading model '{}'".format(filename))

        checkpoint = torch.load(filename) if torch.cuda.is_available() else torch.load(filename, map_location='cpu')

        # For loading external models with different structure in state dict. May cause problems when trying to load optimizer
        if 'model' not in checkpoint.keys():
            temp_checkpoint = {}
            temp_checkpoint['model'] = {k: v for k, v in checkpoint.items()}    # Place entire state_dict inside 'model' key
            del checkpoint
            checkpoint = temp_checkpoint
        return checkpoint
    except FileNotFoundError:
        raise FileNotFoundError(f"=> No model found at '{filename}'")


def net(net_params, inference=False):
    """Define the neural net"""
    model_name = net_params['global']['model_name'].lower()
    num_classes = net_params['global']['num_classes']
    if num_classes == 1:
        warnings.warn("config specified that number of classes is 1, but model will be instantiated"
                      " with a minimum of two regardless (will assume that 'background' exists)")
        num_classes = 2
    msg = f'Number of bands specified incompatible with this model. Requires 3 band data.'
    state_dict_path = ''
    if model_name == 'unetsmall':
        model = unet.UNetSmall(num_classes,
                                       net_params['global']['number_of_bands'],
                                       net_params['training']['dropout'],
                                       net_params['training']['dropout_prob'])
    elif model_name == 'unet':
        model = unet.UNet(num_classes,
                                  net_params['global']['number_of_bands'],
                                  net_params['training']['dropout'],
                                  net_params['training']['dropout_prob'])
    elif model_name == 'ternausnet':
        assert net_params['global']['number_of_bands'] == 3, msg
        model = TernausNet.ternausnet(num_classes)
    elif model_name == 'checkpointed_unet':
        model = checkpointed_unet.UNetSmall(num_classes,
                                       net_params['global']['number_of_bands'],
                                       net_params['training']['dropout'],
                                       net_params['training']['dropout_prob'])
    elif model_name == 'inception':
        model = inception.Inception3(num_classes,
                                     net_params['global']['number_of_bands'])
    elif model_name == 'fcn_resnet101':
        assert net_params['global']['number_of_bands'] == 3, msg
        coco_model = models.segmentation.fcn_resnet101(pretrained=True, progress=True, num_classes=21, aux_loss=None)
        model = models.segmentation.fcn_resnet101(pretrained=False, progress=True, num_classes=num_classes,
                                                  aux_loss=None)
        chopped_dict = chop_layer(coco_model.state_dict(), layer_names=['classifier.4'])
        del coco_model
        # load the new state dict
        # When strict=False, allows to load only the variables that are identical between the two models irrespective of
        # whether one is subset/superset of the other.
        model.load_state_dict(chopped_dict, strict=False)
    elif model_name == 'deeplabv3_resnet101':
        assert net_params['global']['number_of_bands'] == 3, msg
        # pretrained on coco (21 classes)
        coco_model = models.segmentation.deeplabv3_resnet101(pretrained=True, progress=True,
                                                        num_classes=21, aux_loss=None)
        model = models.segmentation.deeplabv3_resnet101(pretrained=False, progress=True,
                                                        num_classes=num_classes, aux_loss=None)
        chopped_dict = chop_layer(coco_model.state_dict(), layer_names=['classifier.4'])
        del coco_model
        model.load_state_dict(chopped_dict, strict=False)
    else:
        raise ValueError(f'The model name {model_name} in the config.yaml is not defined.')

    coordconv_convert = get_key_def('coordconv_convert', net_params['global'], False)
    if coordconv_convert:
        centered = get_key_def('coordconv_centered', net_params['global'], True)
        normalized = get_key_def('coordconv_normalized', net_params['global'], True)
        noise = get_key_def('coordconv_noise', net_params['global'], None)
        radius_channel = get_key_def('coordconv_radius_channel', net_params['global'], False)
        scale = get_key_def('coordconv_scale', net_params['global'], 1.0)
        # note: this operation will not attempt to preserve already-loaded model parameters!
        model = coordconv.swap_coordconv_layers(model, centered=centered, normalized=normalized, noise=noise,
                                                radius_channel=radius_channel, scale=scale)

    if net_params['training']['state_dict_path']:
        state_dict_path = net_params['training']['state_dict_path']
        checkpoint = load_checkpoint(state_dict_path)
    elif inference:
        state_dict_path = net_params['inference']['state_dict_path']
        checkpoint = load_checkpoint(state_dict_path)
    else:
        checkpoint = None

    return model, checkpoint, model_name
