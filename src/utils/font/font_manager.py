import json
import os
from PIL import Image
import numpy as np

""" This file contains classes and functions to manage fonts and make pixel art texts"""

basepath = os.path.dirname(__file__)
fonts_folder = os.path.abspath(os.path.join(basepath, "..", "..","..",
    "ressources","fonts"))

SPACE_WIDTH = 4

all_accents="ÀÁÂÃÄÅÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜàáâãäåèéêëìíîïñòóôõöùúûüÿŸ"
all_special_chars="./-+*&~#’()|_^@[]{}%!?$€:,\`><;\"="
letter_bases={
    "áàâäãå":"a",
    "ÁÀÂÄÃÅ":"A",
    "éèêë"  :"e",
    "ÉÈÊË"  :"E",
    "iíìîï"  :"ı",
    "İÍÌÎÏ"  :"I",
    "óòôöõ" :"o",
    "ÓÒÔÖÕ" :"O",
    "úùûü"  :"u",
    "ÚÙÛÜ"  :"U",
    "ÿ"     :"y",
    "Ÿ"     :"Y",
    "ñ"     :"n",
    "Ñ"     :"N"
}

test_string = "abcdefghijklmnopqrstuvwxyz\ ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789 ./-+*&~#’()|_^@[]{}%!?$€:,\`><;\""
class FontNotFound(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class FontManager():
    """ Class to manage a font """
    def __init__(self,font_name,font_color=None, background_color=None) -> None:
        self.font_name = font_name
        self.image = self.get_image()
        self.json = self.get_json()

        self.image_background_color = self.json["background"]
        self.image_background_color = list(self.image_background_color)
        self.image_background_color.append(255)
        self.image = self.image.convert("RGBA")

        self.max_width = self.json["width"]
        self.max_height = self.json["height"]

        self.set_font_color(font_color)
        self.set_background_color(background_color)

        if self.font_color:
            if self.font_color == self.background_color:
                raise ValueError(f"The font color and background color can't be the same.")

    def set_font_color(self,font_color):
        if not font_color:
            self.font_color = None
            return
        font_color = list(font_color)
        if len(font_color) != 4:
            font_color.append(255)
        self.font_color = font_color

    def set_background_color(self,background_color):
        if not background_color:
            self.background_color = self.image_background_color
            return
        background_color = list(background_color)
        if len(background_color) != 4:
            background_color.append(255)
        self.background_color = background_color

    def get_image(self):
        font_img_path = os.path.join(fonts_folder,self.font_name,self.font_name+".png")
        try:
            font_img = Image.open(font_img_path)
            if font_img.mode != 'RGB':
                raise ValueError("Unsupported image mode: "+font_img.mode)
            return font_img
        except FileNotFoundError as e:
            raise FontNotFound(f"Font '{self.font_name}' was not found.") from e

    def get_json(self):
        font_json_path = os.path.join(fonts_folder,self.font_name,self.font_name+".json")
        try:
            with open(font_json_path,'r') as json_file:
                font_json = json.load(json_file)
            return font_json
        except FileNotFoundError as e:
            raise FontNotFound(f"Font '{self.font_name}' was not found.") from e

    def char_exists(self,char):
        try:
            self.json[char]
            return True
        except KeyError:
            return None

    def get_char_array(self,char):
        """ return a numpy array of the character pixels
        or None if the character isn't in the font"""
        try:
            char_coords = self.json[char]
        except KeyError:
            return None

        x0 = char_coords[0]
        y0 = char_coords[1]
        max_x = char_coords[2]
        max_y = char_coords[3]

        array = np.zeros((self.max_height,max_x,4),dtype=np.uint8)
        array[:,:] = self.background_color
        for y in range(max_y):
            for x in range(max_x):
                pixel_color = self.image.getpixel((x0+x,y0+y))
                if list(pixel_color) != self.image_background_color:
                    if self.font_color:
                        array[y,x] = list(self.font_color)
                    else:
                        array[y,x] = list(pixel_color)
                else:
                    array[y,x] = list(self.background_color)

        return array

class PixelText():
    """ Class to make a pixel text"""
    def __init__(self,text,font_name,font_color=None,background_color=None) -> None:
        self.text = text
        self.font = FontManager(font_name,font_color,background_color)
        self.background_color = self.font.background_color
        self.font_color = self.font.font_color

        self.image_array = []

    def make_array(self):
        """ Change the self.array object to have the numpy array of the text 
         by concatenating numpy arrays of each characters """
        self.image_array = np.zeros((self.font.max_height,1,4),dtype=np.uint8)
        self.image_array[:,:] = self.background_color or [255,255,255,255]

        empty = True
        for char in self.text:
            font_char = self.get_char(char)
            if font_char != None:
                empty=False
                char_array = self.font.get_char_array(font_char)
                self.image_array = np.concatenate((self.image_array,char_array),axis=1)
                self.add_space()

            elif char == " ":
                empty=False
                self.add_space(SPACE_WIDTH)
            
            elif char == "\t":
                empty=False
                self.add_space(2*4)

            elif char == ".":
                empty=False
                self.add_dot()
                self.add_space()

        if empty == True:
            return None
        else:
            return self.image_array
    
    def get_image(self):
        """ Create an image of the class text,
        the image is made by converting the generated numpy array to PIL Image"""
        if self.make_array() is None:
            return None
        # remove excessive space around chars
        while (self.image_array[0,:] == self.background_color).all():
            self.image_array = np.delete(self.image_array,0,0)
        while (self.image_array[-1,:] == self.background_color).all():
            self.image_array = np.delete(self.image_array,-1,0) 

        # add an outline at the top and bottom
        if not (self.image_array[0,:] == self.background_color).all():
            self.add_top_line()

        if not (self.image_array[-1,:] == self.background_color).all():
            self.add_bottom_line()
        
        im = Image.fromarray(self.image_array)
        return im

    def get_char(self,char,from_case=False):

        if char == None:
            return None
        # if the char is valid, we return it
        res = self.font.char_exists(char)
        if res:
            return char

        # check on accent
        if char in all_accents:
            for key in letter_bases:
                if(char in key):
                    letter_base=letter_bases[key]
                    return self.get_char(letter_base)

        # check on case
        if from_case == False: # to avoid infinite recursion
            if char.isupper():
                return self.get_char(char.lower(),True)
            if char.islower():
                return self.get_char(char.upper(),True)
        else:
            return None


    def add_space(self,width=1):
        space = np.zeros((self.font.max_height,1,4),dtype=np.uint8)
        space[:,:] = self.background_color
        for i in range(width):
            self.image_array = np.concatenate((self.image_array,space),axis=1)
    
    def add_bottom_line(self):
        space = np.zeros((1,self.image_array.shape[1],4),dtype=np.uint8)
        space[:,:] = self.background_color
        self.image_array = np.concatenate((self.image_array,space),axis=0)

    def add_top_line(self):
        space = np.zeros((1,self.image_array.shape[1],4),dtype=np.uint8)
        space[:,:] = self.background_color
        self.image_array = np.concatenate((space,self.image_array),axis=0)

    def add_dot(self):
        dot_array = np.zeros((self.font.max_height,self.font.max_width//3,4),dtype=np.uint8)
        dot_array[:,:] = self.background_color
        for i in range(1,(self.font.max_width//3)+1):
            dot_array[-i,:] = self.font_color or [255,255,255,255]
        self.image_array = np.concatenate((self.image_array,dot_array),axis=1)

def get_all_fonts():
    """ Return a list with all the available fonts """
    fonts = []
    for extension in os.listdir(fonts_folder):
        fonts.append(extension)
    return fonts
