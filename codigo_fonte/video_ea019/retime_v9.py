"""Retime complete Blender actions without changing geometry or old sources."""
import bpy

def warp_time(t, points):
    for (a,c),(b,d) in zip(points,points[1:]):
        if t <= b:
            return c+(t-a)*(d-c)/(b-a)
    a,c=points[-2];b,d=points[-1]
    return d+(t-b)*(d-c)/(b-a)

def all_fcurves(action):
    """Blender 4.4+ actions can hold object AND curve/material data slots."""
    found={}
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:found[fc.as_pointer()]=fc
    if not found:
        for fc in action.fcurves:found[fc.as_pointer()]=fc
    return list(found.values())

def retime_actions(points,actions=None):
    for action in actions if actions is not None else bpy.data.actions:
        for fc in all_fcurves(action):
            for k in fc.keyframe_points:
                left,right=k.handle_left.copy(),k.handle_right.copy()
                k.co.x=1+30*warp_time((k.co.x-1)/30,points)
                k.handle_left=(1+30*warp_time((left.x-1)/30,points),left.y)
                k.handle_right=(1+30*warp_time((right.x-1)/30,points),right.y)
            fc.update()
