from .AVSegFormer import AVSegFormer, MAVSNet


def build_model(type, **kwargs):
    if type == 'AVSegFormer':
        return AVSegFormer(**kwargs)
    elif type == 'MAVSNet':
        return MAVSNet(**kwargs)
    else:
        raise ValueError
