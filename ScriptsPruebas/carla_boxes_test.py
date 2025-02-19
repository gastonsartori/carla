import glob
import os
import sys
import argparse
import time
from datetime import datetime
import random
import numpy as np
from numpy import random
from matplotlib import cm
import open3d as o3d
from queue import Queue
from queue import Empty
import logging
import cv2
import math
import json

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla

from camera_utils import build_projection_matrix, w3D_to_cam3D, w3D_to_cam2D, bbox_in_image
from kitti_label import KittiLabel

""" OUTPUT FOLDERS """
OUTPUT_FOLDER = "training"
IMAGES_FOLDER = "image_2"
POINTCLOUDS_FOLDER = "velodyne"
LABELS_FOLDER = "label_2"
CALIB_FOLDER = "calib"

LIST_VEHICLES_PATH = "../Unreal/CarlaUE4/LidarModelFiles/vehicles.json"

""" SAVE PATHS """
LIDAR_PATH = os.path.join(OUTPUT_FOLDER, 'velodyne/{0:06}.bin')
LABEL_PATH = os.path.join(OUTPUT_FOLDER, 'label_2/{0:06}.txt')
IMAGE_PATH = os.path.join(OUTPUT_FOLDER, 'image_2/{0:06}.png')
CALIBRATION_PATH = os.path.join(OUTPUT_FOLDER, 'calib/{0:06}.txt')


def sensor_callback(data,queue):
    queue.put(data)


def create_output_folders():
    current_datetime = datetime.now().strftime("%d-%m-%y_%X")
    output_directory = os.path.join(current_datetime,OUTPUT_FOLDER)

    images_path = create_folder(output_directory, IMAGES_FOLDER)
    pointcloud_path = create_folder(output_directory, POINTCLOUDS_FOLDER)
    calib_path = create_folder(output_directory, CALIB_FOLDER)
    labels_path = create_folder(output_directory, LABELS_FOLDER)

    return images_path,pointcloud_path,calib_path,labels_path

def create_folder(output_directory,folder):
    output_folder = os.path.join(output_directory,folder)
    os.makedirs(output_folder)

    return output_folder

def generate_lidar_bp(blueprint_library,delta):
    lidar_bp = blueprint_library.find('sensor.lidar.ray_cast')
    lidar_bp.set_attribute('upper_fov', str(2.0))
    lidar_bp.set_attribute('lower_fov', str(-24.8))
    lidar_bp.set_attribute('channels', str(64))
    lidar_bp.set_attribute('range', str(120))
    lidar_bp.set_attribute('rotation_frequency', str(1.0 / delta))
    lidar_bp.set_attribute('points_per_second', str(1300000))
    lidar_bp.set_attribute('noise_stddev', str(0.01))
    lidar_bp.set_attribute('dropoff_general_rate',str(0.0))
    lidar_bp.set_attribute('dropoff_intensity_limit',str(0.0))
    lidar_bp.set_attribute('dropoff_zero_intensity',str(0.0))
    #lidar_bp.set_attribute('sensor_tick', str(0.1)) #si es el doble q delta, va a dar un dato cada 2 ticks
    return lidar_bp

def generate_camera_bp(blueprint_library):
    camera_bp = blueprint_library.filter("sensor.camera.rgb")[0]
    camera_bp.set_attribute("image_size_x", str(1242)) #Resolucion de las imagenes de Kitti
    camera_bp.set_attribute("image_size_y", str(375))

    return camera_bp

def spawn_vehicles(spawn_points,number_of_vehicles,vehicles_bp,traffic_manager,client):
    SpawnActor = carla.command.SpawnActor
    SetAutopilot = carla.command.SetAutopilot
    FutureActor = carla.command.FutureActor
    vehicles_list = []

    batch = []
    for n, transform in enumerate(spawn_points):
        if n >= number_of_vehicles:
            break
        blueprint = random.choice(vehicles_bp)
        if blueprint.has_attribute('color'):
            color = random.choice(blueprint.get_attribute('color').recommended_values)
            blueprint.set_attribute('color', color)
        if blueprint.has_attribute('driver_id'):
            driver_id = random.choice(blueprint.get_attribute('driver_id').recommended_values)
            blueprint.set_attribute('driver_id', driver_id)
        blueprint.set_attribute('role_name', 'autopilot')

        batch.append(SpawnActor(blueprint, transform)
            .then(SetAutopilot(FutureActor, True, traffic_manager.get_port())))

    for response in client.apply_batch_sync(batch, True):
        if response.error:
            logging.error(response.error)
        else:
            vehicles_list.append(response.actor_id)

    return vehicles_list

def save_image(images_path, image_data):
    image_path =  './%s/%.6d.png' % (images_path, image_data.frame)
    image_data.save_to_disk(image_path)
    #print('imagen %.6d.bin guardada' % image_data.frame)

def save_pointcloud(pointclouds_path,pointcloud):
    pc = np.copy(np.frombuffer(pointcloud.raw_data, dtype=np.dtype('f4')))
    pc = np.reshape(pc, (int(pc.shape[0] / 4), 4))
    pointcloud_path = './%s/%.6d.bin' % (pointclouds_path, pointcloud.frame) 
    pc.tofile(pointcloud_path)
    #print('point cloud %.6d.bin guardada' % lidar_data.frame)

def is_in_image(npc,K,w2c,image_w,image_h):
    """ Determinar si el vehiculo npc se enceuntra dentro de los limites de la imagen """

    npc_center_world_pos = get_center_world_pos(npc)
    npc_center_image_pos = w3D_to_cam2D(npc_center_world_pos,K,w2c)

    return (npc_center_image_pos[0] > 0.0 and  npc_center_image_pos[0] < image_w and \
            npc_center_image_pos[1] > 0.0 and  npc_center_image_pos[1] < image_h  )

def is_in_front(vehicle,npc):
    """ Determinar si el actor se encuentra al frente del vehiculo q posee la camara """

    #Prod punto entre el forward vector del vehiculo y el vector entre el vehiculo y el actor
    forward_vec = vehicle.get_transform().get_forward_vector()
    ray = npc.get_transform().location - vehicle.get_transform().location

    #si el prod punto es mayor a 1, significa q el actor esta al frente del vehiculo
    return (forward_vec.dot(ray) > 1)


def get_center_world_pos(vehicle):
    vehicle_world_pos = vehicle.get_transform().location
    vehicle_world_pos.z += vehicle.bounding_box.extent.z

    return vehicle_world_pos

def load_list_of_vehicles():
    file = open(LIST_VEHICLES_PATH)
    data=json.load(file)
    file.close()

    list_of_vehicles=[]
    for vehicle_id in data['vehicles']:
        list_of_vehicles.append(vehicle_id['api_bp_name'])

    return list_of_vehicles

def main(arg):
    """Spawnea el LIDAR HDL-64E y una camara RGB en un vehiculo, y genera un paso de simulacion"""
    #Cliente y simulador
    client = carla.Client('localhost', 2000)
    client.set_timeout(2.0)
    world = client.get_world()

    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
    
    #Crear directorios para guardar los datos, nubes de puntos, imagenes y labels
    images_path,pointclouds_path,calib_path,labels_path = create_output_folders()

    try:
        #Setea modo sincrono en la simulacion con delta fijo
        original_settings = world.get_settings()
        settings = world.get_settings()

        #traffic manager
        traffic_manager = client.get_trafficmanager(8000)
        traffic_manager.set_synchronous_mode(True)
        traffic_manager.set_global_distance_to_leading_vehicle(2.5) #distancia a mantener entre vehiculos
        #traffic_manager.set_hybrid_physics_mode(True) #desactiva las fisicas de los vehiculos lejanos al vehiculo hero, reduce el computo
        #traffic_manager.set_hybrid_physics_radius(100.0) #dentro de este radio, si se calculan las fisicas
        
        delta = 0.05
        #delta = 0.1
        settings.fixed_delta_seconds = delta
        settings.synchronous_mode = True
        world.apply_settings(settings)
        
        blueprint_library = world.get_blueprint_library()

        #Crea el LIDAR con las especificaciones de HDL-64E
        lidar_bp = generate_lidar_bp(blueprint_library,delta)

        #Crea la camara RGB
        camera_bp = generate_camera_bp(blueprint_library)

        #Crea vehiculo sobre el cual montar los sensores
        vehicle_bp = blueprint_library.filter("vehicle.lincoln.mkz_2017")[0]
        #vehicle_bp.set_attribute('role_name', 'hero')
        vehicle_bp.set_attribute('role_name', 'autopilot')

        #Spawnear vehiculo y sensores
        sp_vehicle = 0

        vehicle_transform = world.get_map().get_spawn_points()[sp_vehicle]
        vehicle = world.spawn_actor(
            blueprint=vehicle_bp,
            transform=vehicle_transform)
        vehicle.set_autopilot(True)

        #las coordenadas son relativas al vehiculo
        #x es el eje correspondiente a la direccion del auto, positivo seria hacia adelante
        #z es la altura
        camera = world.spawn_actor(blueprint=camera_bp,
            transform=carla.Transform(carla.Location(x=0.0, z=1.65)), #posicion segun Kitti 
            attach_to=vehicle)

        lidar = world.spawn_actor(
            blueprint=lidar_bp,
            transform=carla.Transform(carla.Location(x=-0.27, z=1.73)), #posicion segun Kitti
            attach_to=vehicle)

        #Funciones de callback para almacenar imagen y nube de puntos
        image_queue= Queue()
        lidar_queue= Queue()

        #Al recibir un nuevo data, se almacena en la cola
        lidar.listen(lambda data: sensor_callback(data,lidar_queue))
        camera.listen(lambda data: sensor_callback(data,image_queue))
        
        #spawnear trafico 
        list_of_vehicles = load_list_of_vehicles()

        vehicles_bp = blueprint_library.filter('vehicle.*') #blueprints de todos los vehiculos
        vehicles_bp = [x for x in vehicles_bp if x.id.endswith(tuple(list_of_vehicles)) ]
        #print(vehicles_bp)
        
        vehicles_bp = sorted(vehicles_bp, key=lambda bp: bp.id)
        spawn_points = world.get_map().get_spawn_points() #puntos de spawn del mapa en uso
        spawn_points.pop(sp_vehicle) #se quita el punto en el que se spawnea el vehivulo con los sensores
        random.shuffle(spawn_points) #mezclar 

        number_of_vehicles = 30

        vehicles_list = spawn_vehicles(spawn_points, number_of_vehicles, vehicles_bp, traffic_manager,client)

        #generar los ticks de simulacion necesarios hasta capturar los frames necesarios

        frames = arg.frames
        frames_captured = 0
        ticks = 0

        # Retrieve the first image
        world.tick()

        # Calculate the camera projection matrix to project from 3D -> 2D
        image_w = camera_bp.get_attribute("image_size_x").as_int()
        image_h = camera_bp.get_attribute("image_size_y").as_int()
        fov = camera_bp.get_attribute("fov").as_float()
        K = build_projection_matrix(image_w, image_h, fov)
        

        while frames_captured < frames:

            world.tick()
            ticks += 1
            time.sleep(0.1)

            #tras cada tick, en caso de haber dato disponible, se lo obtiene
            if not image_queue.empty():
                image = image_queue.get()
                
            if not lidar_queue.empty():
                pointcloud = lidar_queue.get()
            

            #cuando se tengan ambos datos (imagen y nube de puntos) de un mismo frame, se almacenan ambos
            if ticks > 1 and (image.frame == pointcloud.frame):

                #guardar imagen
                save_image(images_path,image)

                #guardar nube de puntos
                save_pointcloud(pointclouds_path,pointcloud)

                frames_captured = frames_captured + 1 

                #crear archivo de label
                label_file_name = './%s/%.6d.txt' % (labels_path, pointcloud.frame)
                label_file = open(label_file_name,'w')

                sys.stdout.write("\r Capturados %d frames de %d" % (frames_captured,frames) + ' ')
                sys.stdout.flush()

                # Posicion de la camara para transformar coordenadas
                world_2_camera = np.array(camera.get_transform().get_inverse_matrix())

                #Obtener todos los actores "vehiculos" y para cada uno
                for npc in world.get_actors().filter('*vehicle*'):
                    if npc.id != vehicle.id:
                        
                        #se determina si el npc se encuentra en frente del vehiculo
                        npc_is_in_front = is_in_front(vehicle,npc)

                        #se calcula la distancia entre los vehiculos
                        dist = npc.get_transform().location.distance(vehicle.get_transform().location)

                        #Solo se computan las bounding boxes de actores en frente y que esten a menos de una cierta distancia
                        if npc_is_in_front and dist < 50:
                            
                            #se determina si el centro del vehiculo aparece dentro de los limites de la imagen
                            npc_is_in_image = is_in_image(npc,K,world_2_camera,image_w,image_h)

                            if(npc_is_in_image):
                                
                                #Se crea el label de este npc y se obtiene la informacion necesaria
                                label = KittiLabel()

                                #Type
                                label.set_type('Car')

                                #Location
                                #Se obtiene la posicion del centro del vehiculo en coordenadas world3D
                                npc_world_center_pos = get_center_world_pos(npc)
                                #Se tranforma de world-3D a camara-2D
                                location = w3D_to_cam3D(npc_world_center_pos,world_2_camera)
                                label.set_location(location)

                                #Dimensions
                                #Se obtiene la bounding box del actor
                                bb = npc.bounding_box
                                #print(bb)
                                #https://carla.readthedocs.io/en/0.9.5/measurements/
                                length=bb.extent.x*2    #extent.x es la mitad del largo del bb
                                width=bb.extent.y*2     #extent.y es la mitad del ancho del bb
                                height=bb.extent.z*2    #extent.z es la mitad del alto del bb
                                #print(length)
                                #print(width)
                                #print(height)
                                dimensions = [height, width, length]
                                label.set_dimensions(dimensions)

                                #Bbox 2D

                                #obtener vertices del bb en 2D
                                verts = [v for v in bb.get_world_vertices(npc.get_transform())]
                                verts_x = []
                                verts_y = []
                                for vert in verts:
                                    vert_2D = w3D_to_cam2D(vert, K, world_2_camera)
                                    verts_x.append(vert_2D[0])
                                    verts_y.append(vert_2D[1])

                                #Coordenada mas a la izquierda
                                left_limit = min(verts_x)
                                #Coordenada mas a la derecha
                                rigth_limit = max(verts_x)
                                #Coordenada mas arriba
                                high_limit = min(verts_y)
                                #Coordenada mas abajo
                                low_limit = max(verts_y)
                                
                                #en los min y max, ya se tienen los vertices 2D
                                bbox_2D = [left_limit, high_limit, rigth_limit, low_limit]

                                #Chequear si los limites estan fuera de la imagen, en tal caso llevarlo al valor minimo o maximo segun corresponda
                                safe_bbox_2D = bbox_in_image(bbox_2D,image_w,image_h)
                                label.set_bbox(safe_bbox_2D)

                                #rotation_y
                                #https://blog.csdn.net/qq_16137569/article/details/118873033
                                rot_npc= npc.get_transform().rotation.yaw
                                rot_vehicle = vehicle.get_transform().rotation.yaw

                                rot_y = (rot_vehicle - rot_npc + 90.0) 

                                if(rot_y > 180.0):
                                    rot_y -= 360.0

                                if(rot_y < -180.0):
                                    rot_y += 360.0

                                rot_y_rad = math.radians(rot_y)#de grados a radianes
                                
                                label.set_rotation_y(rot_y_rad)

                                #Alpha 
                                #https://arxiv.org/abs/2112.04421
                                #Se lo calcula a partir de la rot_y y location
                                #location = [x,y,z]
                                #alpha = rot_y - arctan(x/z)
                                alpha = rot_y_rad - math.atan(location[0]/location[2])
                                
                                if(alpha > math.pi):
                                    alpha -= 2*math.pi

                                if(alpha < -math.pi):
                                    alpha += 2*math.pi   

                                label.set_alpha(alpha)

                                #Truncated
                                #TODO

                                #Occluded
                                #TODO

                                str_label = label.get_label()
                                label_file.write("{}\n".format(str_label))
                
                label_file.close()

    finally:
        world.apply_settings(original_settings)
        vehicle.destroy()
        lidar.destroy()
        camera.destroy()
        cv2.destroyAllWindows()

        client.apply_batch([carla.command.DestroyActor(x) for x in vehicles_list])
        time.sleep(0.5)

if __name__ == "__main__":
    argparser = argparse.ArgumentParser(
        description=__doc__)
    argparser.add_argument(
        '-f', '--frames',
        default=10,
        type=int,
        help='cantidad de frames a capturar, default: 10')
    args = argparser.parse_args()

    try:
        main(args)
    except KeyboardInterrupt:
        print(' - Exited by user.')
