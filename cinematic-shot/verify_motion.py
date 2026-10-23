"""Check the real scene state, rewind behavior and nearest no-motion controls.

Run inside Blender. No image render or original experiment mutation occurs.
"""
import sys,json,hashlib,math
from pathlib import Path
import bpy
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import shot_scene as shot

scene=shot.build_shot_scene()
water=bpy.data.objects['WATER_still_ripples']
mist=bpy.data.materials['MAT_mist_volume'].node_tree.nodes
material=bpy.data.materials['MAT_teal_inlet_water'].node_tree.nodes
def snapshot(t):
    shot.set_time(scene,t);bpy.context.view_layer.update()
    return {'water':np.array([v.co[:] for v in water.data.vertices]),'camera':np.array(scene.camera.matrix_world),
            'mist':np.array(mist['CINEMATIC_mist_advect'].inputs['Location'].default_value[:]),
            'normals':np.array(material['CINEMATIC_water_drift'].inputs['Location'].default_value[:])}
zero=snapshot(0);five=snapshot(5);again=snapshot(0)
checks=[]
def check(name,condition,**detail):
    checks.append({'name':name,'pass':bool(condition),**detail})
for name in zero:check(name+'_rewinds_exactly',np.array_equal(zero[name],again[name]))
for name in zero:check(name+'_changes_with_time',not np.array_equal(zero[name],five[name]))
xy=five['water'][:,:2];expected=np.zeros(len(xy))
for w in shot.WAVES:
    omega=np.sqrt(shot.GRAVITY*np.hypot(w['kx'],w['ky']))
    expected+=w['amplitude']*np.sin(w['kx']*xy[:,0]+w['ky']*xy[:,1]-omega*.42*5+w['phase'])
error=float(np.max(np.abs(five['water'][:,2]-expected)))
check('all_water_vertices_match_independent_vectorized_formula',error<1e-7,max_abs=error,vertices=len(xy))
check('water_amplitude_bound',float(np.max(np.abs(five['water'][:,2])))<=sum(w['amplitude'] for w in shot.WAVES)+1e-7)
check('water_base_world_height',abs(water.location.z-(-.04))<1e-7)
check('mist_mapping_matches_time',np.allclose(five['mist'],np.array(shot.MIST_DRIFT)*5))
check('fine_normals_mapping_matches_time',np.allclose(five['normals'],np.array(shot.WATER_SHADER_DRIFT)*5))
check('camera_midpoint',np.allclose(five['camera'][:3,3],[.625,-17,1.5]))
# Freeze the animation clocks while retaining the real renderer objects.
old_speed=shot.WAVE_TIME_SCALE;old_mist=shot.MIST_DRIFT;old_normal=shot.WATER_SHADER_DRIFT;old_cam=shot._animate_camera
shot.WAVE_TIME_SCALE=0.;shot.MIST_DRIFT=(0.,0.,0.);shot.WATER_SHADER_DRIFT=(0.,0.,0.)
shot._animate_camera=lambda camera,t:old_cam(camera,0.)
held0=snapshot(0);held5=snapshot(5)
for name in held0:check(name+'_no_motion_control',np.array_equal(held0[name],held5[name]))
shot.WAVE_TIME_SCALE=old_speed;shot.MIST_DRIFT=old_mist;shot.WATER_SHADER_DRIFT=old_normal;shot._animate_camera=old_cam
restored=snapshot(5)
for name in restored:check(name+'_restored_after_control',np.array_equal(restored[name],five[name]))
wet=bpy.data.materials['MAT_cinematic_wet_foreground'].node_tree.nodes
geo=wet['CINEMATIC_wet_world_position'];rough=wet['CINEMATIC_wet_roughness_by_height'];coat=wet['CINEMATIC_wet_coat_by_height']
check('wetness_uses_shader_geometry_position',geo.bl_idname=='ShaderNodeNewGeometry')
check('wetness_roughness_endpoints',np.allclose([rough.inputs[k].default_value for k in ('From Min','From Max','To Min','To Max')],[-.3,1.2,.11,.58]) and rough.clamp)
check('wetness_coat_endpoints',np.allclose([coat.inputs[k].default_value for k in ('To Min','To Max')],[.42,.12]) and coat.clamp)
original=hashlib.sha256((HERE.parent/'scene.py').read_bytes()).hexdigest()
check('original_scene_preserved',original=='03484bd17d1f9c3e0a280c0d1302462181d1b1ec1e348d643232afb1faa6562c')
result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','checks':checks,'blender':bpy.app.version_string,'scope':'Geometry/node/camera state checks, not a validation of physical water or fog dynamics','units':'Scene units; metre labels in development metadata denote an assumed scale, not physical calibration','source_sha256':hashlib.sha256((HERE/'shot_scene.py').read_bytes()).hexdigest()}
(HERE/'qa').mkdir(exist_ok=True)
(HERE/'qa/MOTION_CHECKS.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if result['status']!='PASS':raise RuntimeError('Motion verification failed')
