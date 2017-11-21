import os
#!/usr/bin/env python3

# Copyright (c) 2017 Computer Vision Center (CVC) at the Universitat Autonoma de
# Barcelona (UAB), and the INTEL Visual Computing Lab.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

"""
Class used for operating the city map 

"""

try:
    import numpy as np
except ImportError:
    raise RuntimeError('cannot import numpy, make sure numpy package is installed')

try:
	from PIL import Image
except ImportError:
	raise RuntimeError('cannot import PIL, make sure pillow package is installed')


import math

def string_to_node(string):
	vec = string.split(',')
	return (int(vec[0]),int(vec[1]))

def string_to_floats(string):
	vec = string.split(',')

	return (float(vec[0]),float(vec[1]),float(vec[2]))



class CarlaMap(object):


	def __init__(self,city):


		dir_path = os.path.dirname(__file__)
		city_file = dir_path+'/' + city + '.txt'
		city_map_file = dir_path+'/' + city + '.png'

		with  open(city_file, 'r') as file:

			linewordloffset = file.readline()
			# The offset of the world from the zero coordinates ( The coordinate we consider zero)
			self.worldoffset = string_to_floats(linewordloffset)

			lineworldangles = file.readline()
			self.angles =  string_to_floats(lineworldangles)

			self.worldrotation = np.array([[math.cos(math.radians(self.angles[2])),-math.sin(math.radians(self.angles[2])) ,0.0],[math.sin(math.radians(self.angles[2])),math.cos(math.radians(self.angles[2])),0.0],[0.0,0.0,1.0]])

			# Ignore for now, these are offsets for map coordinates and scale ( Not used)
			lineworscale = file.readline()
			linemapoffset = file.readline()

			# The offset of the map zero coordinate
			self.mapoffset =  string_to_floats(linemapoffset)		

			# the graph resolution.
			linegraphres = file.readline()
			self.resolution =  string_to_node(linegraphres)	

		# The number of game units per pixel 
		self.pixel_density = 16.43
		self.map_image = Image.open(city_map_file)
		self.map_image.load()
		self.map_image = np.asarray(self.map_image, dtype="int32" )		



	def draw_position_on_map(self,position,color,size=20):

		position = self.get_position_on_map([position.x,position.y,position.z])
		for i in range(0,size):
			self.map_image[int(position[1]),int(position[0])]=color
			self.map_image[int(position[1])+i,int(position[0])]=color
			self.map_image[int(position[1]),int(position[0])+i]=color
			self.map_image[int(position[1])-i,int(position[0])]=color
			self.map_image[int(position[1]),int(position[0])-i]=color
			self.map_image[int(position[1])+i,int(position[0])+i]=color
			self.map_image[int(position[1])-i,int(position[0])-i]=color
			self.map_image[int(position[1])+i,int(position[0])-i]=color
			self.map_image[int(position[1])-i,int(position[0])+i]=color


	def get_map(self,size=None):
		if size != None:
			img = Image.fromarray(self.map_image.astype(np.uint8))
			img = img.resize((size[1],size[0]), Image.ANTIALIAS)
			img.load()
			return np.fliplr(np.asarray( img, dtype="int32"))
		return np.fliplr(self.map_image)


	# get the position on the map for a certain world position

	def get_position_on_map(self,world):

		relative_location = []
		pixel=[]

		rotation = np.array([world[0],world[1],world[2]])
		rotation = rotation.dot(self.worldrotation)



		relative_location.append(rotation[0] + self.worldoffset[0] - self.mapoffset[0])
		relative_location.append(rotation[1] + self.worldoffset[1] - self.mapoffset[1])
		relative_location.append(rotation[2] + self.worldoffset[2] - self.mapoffset[2])

	
		pixel.append(math.floor(relative_location[0]/float(self.pixel_density)))
		pixel.append(math.floor(relative_location[1]/float(self.pixel_density)))

		return pixel

	# Get world position of a certain map position

	def get_position_on_world(self,pixel):

		relative_location =[]
		world_vertex = []	
		relative_location.append(pixel[0]*self.pixel_density)
		relative_location.append(pixel[1]*self.pixel_density)

		world_vertex.append(relative_location[0]+self.mapoffset[0] -self.worldoffset[0])
		world_vertex.append(relative_location[1]+self.mapoffset[1] -self.worldoffset[1])
		world_vertex.append(22) # Z does not matter for now

		return world_vertex


	# Get the lane orientation of a certain world position

	def get_lane_orientation(self,world):

		relative_location = []
		pixel=[]
		rotation = np.array([world[0],world[1],world[2]])
		rotation = rotation.dot(self.worldrotation)

		
		relative_location.append(rotation[0] + self.worldoffset[0] - self.mapoffset[0])
		relative_location.append(rotation[1] + self.worldoffset[1] - self.mapoffset[1])
		relative_location.append(rotation[2] + self.worldoffset[2] - self.mapoffset[2])


		pixel.append(math.floor(relative_location[0]/float(self.pixel_density)))
		pixel.append(math.floor(relative_location[1]/float(self.pixel_density)))


		ori = self.map_image[int(pixel[1]),int(pixel[0]),2]
		ori = ((float(ori)/255.0) ) *2*math.pi 



		return (-math.cos(ori),-math.sin(ori))