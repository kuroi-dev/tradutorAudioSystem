import tkinter as tk 
import threading 
import pystray 
from PIL import Image, ImageDraw

print("HOLA")

# Crear ventana 
root = tk.Tk() 
root.title("Mi Aplicativo") 
root.geometry("300x200")

# Funciones para mostrar/ocultar 
def show_window(): 
    root.deiconify() 
def hide_window(): 
    root.withdraw()

def create_image(): 
    image = Image.new("RGB", (64, 64), "black") 
    dc = ImageDraw.Draw(image) 
    dc.rectangle((16, 16, 48, 48), fill="white") 
    return image

def on_quit(icon,item):
    icon.stop()
    root.quit()

icon = pystray.Icon("Miapp" , create_image(), menu = pystray.Menu(
    pystray.MenuItem("Mostrar", lambda: show_window()),
    pystray.MenuItem("Ocultar", lambda: hide_window()),
    pystray.MenuItem("Salir", on_quit)
))

def run_icon():
    icon.run()

threading.Thread(target=run_icon,daemon=True).start()

hide_window()
root.mainloop()
