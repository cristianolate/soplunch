import cgi
import os
from datetime import date

from google.appengine.api import users
from google.appengine.api import mail
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

DIAS = ['Lunes', 'Martes', 'Mi&eacute;rcoles', 'Jueves', 'Viernes', 'S&aacute;bado', 'Domingo']
MENSAJES = {'menu_creado'		:	'Menu creado y notificaciones enviadas.',
			'bienvenida'		:	'Bienvenido a Almorzando con Soporta... bon app&eacute;tit!',
			'mail_body'			:	'Ingrese a http://soplunch.appspot.com/pedido para escoger menu. Y que sea antes de las 12:30 (hora continental), porque a esa hora se envian los pedidos. Si no lo hace, se queda debajo de la mesa.',
			'mail_titulo'		:	'Almorzando con Soporta',
			'no_invitado'		:	'Lo sentimos, pero Ud. no ha sido invitado a comer hoy.',
			'eleccion_enviada'	:	'Su preferencia para el almuerzo ha sido enviada.'}

class Comensal(db.Model):
	usuario = db.UserProperty()

class Entrada(db.Model):
	nombre = db.StringProperty()
	descripcion = db.StringProperty()

class Fondo(db.Model):
	nombre = db.StringProperty()
	descripcion = db.StringProperty()

class Agregado(db.Model):
	nombre = db.StringProperty()
	descripcion = db.StringProperty()

class Menu(db.Model):
	fecha = db.DateProperty(required=True, auto_now_add=True)
	entradas = db.ListProperty(str)
	fondos = db.ListProperty(str)
	agregados = db.ListProperty(str)
	comensales = db.ListProperty(users.User)

class Eleccion(db.Model):
	fecha = db.DateProperty(required=True, auto_now_add=True)
	usuario = db.UserProperty()
	entrada = db.StringProperty()
	fondo = db.StringProperty()
	agregado = db.StringProperty()

"""
	Funcion para construir una salida con la lista de elementos 
	para autocompletar
"""
def my_join(query):
	lista = []
	for item in query:
		lista.append(item.nombre)
	return "[\'" + "\', \'".join(lista) + "\']"

class MainPage(webapp.RequestHandler):
	def get(self):
		usuario = users.get_current_user()
		url_salir = users.create_logout_url(self.request.uri)

		if usuario:
			tmpl_vals = {'usuario'		: usuario,
						 'url_salir'	: url_salir,
						 'the_message'	: MENSAJES['bienvenida']}	
			path = os.path.join(os.path.dirname(__file__), 'tmpl/simple.html')
			self.response.out.write(template.render(path, tmpl_vals))
		else:
			self.redirect(users.create_login_url(self.request.uri))


class Almuerzo(webapp.RequestHandler):
	def get(self):
		usuario = users.get_current_user()
		hoy = date.today()
		url_salir = users.create_logout_url(self.request.uri)
		dia = DIAS[hoy.weekday()]

		if (usuario and users.is_current_user_admin()):
			lista = []
			for item in Comensal.all():
				lista.append(item.usuario.email())

			comensales = "[\'" + "\', \'".join(lista) + "\']"
			entradas = my_join(Entrada.all())
			fondos = my_join(Fondo.all())
			agregados = my_join(Agregado.all())

			tmpl_vals = {'comensales'	: comensales, 
						 'entradas'		: entradas,
						 'fondos'		: fondos,
						 'agregados'	: agregados, 
						 'dia'			: dia,
						 'url_salir'	: url_salir,
						 'usuario'		: usuario}
			path = os.path.join(os.path.dirname(__file__), 'tmpl/crear.html')
			self.response.out.write(template.render(path, tmpl_vals))
		elif usuario:
			tmpl_vals = {'url_salir'  : url_salir,
						 'usuario'    : usuario,
						 'the_message': MENSAJES['bienvenida']}	
			path = os.path.join(os.path.dirname(__file__), 'tmpl/simple.html')
			self.response.out.write(template.render(path, tmpl_vals))
		else:
			self.redirect(users.create_login_url(self.request.uri))


	def post(self):
		usuario = users.get_current_user()
		hoy = date.today()
		dia = DIAS[hoy.weekday()]
		fkey = str(hoy.year) + str(hoy.month) + str(hoy.day) # Fecha a lo 'yyyymmdd'
		url_salir = users.create_logout_url(self.request.uri)

		menu = Menu(key_name=fkey)

		# Guardo los comensales para futuros ingresos
		for item in self.request.get('comensales').split(','):
			comen = Comensal(key_name=item.strip())
			comen.usuario = users.User(item.strip())
			comen.put()
			menu.comensales.append(users.User(item.strip()))
		
		# Guardo las entradas para futuros ingresos
		for item in self.request.get('entradas').split(','):
			entrada = Entrada(key_name=item.strip())
			entrada.nombre = item.strip()
			entrada.put()
			menu.entradas.append(entrada.nombre)

		# Guardo los fondos para futuros ingresos
		for item in self.request.get('fondos').split(','):
			fondo = Fondo(key_name=item.strip())
			fondo.nombre = item.strip()
			fondo.put()
			menu.fondos.append(fondo.nombre)

		# Guardo los agregados para futuros ingresos
		for item in self.request.get('agregados').split(','):
			agregado = Agregado(key_name=item.strip())
			agregado.nombre = item.strip()
			agregado.put()
			menu.agregados.append(agregado.nombre)

		# Guardo el menu de hoy
		menu.put()

		# Antes de crear registros para elecciones, elimino posibles existentes
		query = Eleccion.gql("WHERE fecha = :1", hoy)
		for item in query:
			item.delete()

		# Por cada comensal, creo un elemento Eleccion (para que despues elija)
		for comensal in menu.comensales:
			eleccion = Eleccion(key_name=fkey + comensal.email())
			eleccion.fecha = hoy
			eleccion.usuario = comensal
			eleccion.put()

		# Envio el mail a cada comensal
		notificacion = mail.EmailMessage()
		notificacion.sender = 'cristian.olate@gmail.com'
		notificacion.body = MENSAJES['mail_body']
		notificacion.subject = MENSAJES['mail_titulo']
		for comensal in menu.comensales:
			notificacion.to = comensal.email()
			notificacion.send()

		tmpl_vals = {'url_salir'	: url_salir,
					 'usuario'		: usuario,
					 'the_message'	: MENSAJES['menu_creado']}	
		path = os.path.join(os.path.dirname(__file__), 'tmpl/simple.html')
		self.response.out.write(template.render(path, tmpl_vals))

class Pedido(webapp.RequestHandler):
	def get(self):
		hoy = date.today()
		usuario = users.get_current_user()
		url_salir = users.create_logout_url(self.request.uri)
		dia = DIAS[hoy.weekday()]

		if usuario:
			query = Eleccion.gql("WHERE fecha = :1 AND usuario = :2", hoy, usuario)
			elec = query.get()

			if elec:
				query = Menu.gql("WHERE fecha = :1", hoy)
				menu = query.get()
				entradas = menu.entradas
				fondos = menu.fondos
				agregados = menu.agregados
				tmpl_vals = {'comensal'		: usuario.email(),
							 'entradas'		: entradas,
							 'fondos'		: fondos,
							 'agregados'	: agregados, 
							 'dia'			: dia,
							 'url_salir'	: url_salir,
							 'usuario'		: usuario}
				path = os.path.join(os.path.dirname(__file__), 'tmpl/ordenar.html')
				self.response.out.write(template.render(path, tmpl_vals))
			else:
				tmpl_vals = {'url_salir'	: url_salir,
							 'usuario'		: usuario,
							 'the_message'	: MENSAJES['no_invitado']}	
				path = os.path.join(os.path.dirname(__file__), 'tmpl/simple.html')
				self.response.out.write(template.render(path, tmpl_vals))
		else:
			self.redirect(users.create_login_url(self.request.uri))

	def post(self):
		usuario = users.get_current_user()
		hoy = date.today()
		fkey = str(hoy.year) + str(hoy.month) + str(hoy.day)
		url_salir = users.create_logout_url(self.request.uri)

		elec = Eleccion(key_name=fkey + usuario.email())
		elec.fecha = hoy
		elec.usuario = usuario
		elec.entrada = self.request.get('entrada')
		elec.fondo = self.request.get('fondo')
		elec.agregado = self.request.get('agregado')

		elec.put()

		tmpl_vals = {'url_salir'	: url_salir,
					 'usuario'		: usuario,
					 'the_message'	: MENSAJES['eleccion_enviada']}	
		path = os.path.join(os.path.dirname(__file__), 'tmpl/simple.html')
		self.response.out.write(template.render(path, tmpl_vals))

class Resumen(webapp.RequestHandler):
	def get(self):
		hoy = date.today()
		dia = DIAS[hoy.weekday()]
		usuario = users.get_current_user()
		url_salir = users.create_logout_url(self.request.uri)

		if usuario:
			# Esto es para contar las elecciones de entradas y fondo+agregado
			# Esto debe dejarse mejor hecho.
			elecs = Eleccion.gql("WHERE fecha = :1", hoy)
			lista_entradas = []
			lista_fondos = []
			for el in elecs:
				if (el.entrada):
					lista_entradas.append(el.entrada)
					lista_fondos.append(el.fondo + ' con ' + el.agregado)

			# Se crear un diccionario para entradas y fondo+agregado, con la cuenta
			cuentas_entradas = {}
			for ent in lista_entradas:
				cuentas_entradas[ent] = lista_entradas.count(ent)
			cuentas_fondos = {}
			for fon in lista_fondos:
				cuentas_fondos[fon] = lista_fondos.count(fon)

			# Luego se crea el string de salida para mostrar
			msg_entradas = ''
			msg_fondos = ''
			for item in cuentas_entradas.keys():
				msg_entradas = msg_entradas + item + ': ' + str(cuentas_entradas[item]) + '<br/>'

			for item in cuentas_fondos.keys():
				msg_fondos = msg_fondos + item + ': ' + str(cuentas_fondos[item]) + '<br/>'

			elecciones = Eleccion.gql("WHERE fecha = :1", hoy)
			tmpl_vals = {'dia'			: dia,
						 'url_salir'	: url_salir,
						 'usuario'		: usuario,
						 'elecciones'	: elecciones, 
						 'msg_entradas'	: msg_entradas,
						 'msg_fondos'	: msg_fondos}
			path = os.path.join(os.path.dirname(__file__), 'tmpl/resumen.html')
			self.response.out.write(template.render(path, tmpl_vals))

class Dieta(webapp.RequestHandler):
	def get(self):
		hoy = date.today()
		usuario = users.get_current_user()
		url_salir = users.create_logout_url(self.request.uri)

		if(usuario):
			# Esto es para contar las elecciones de entradas, fondos y agregados
			elecs = Eleccion.gql("WHERE usuario = :1", usuario)
			lista_entradas = []
			lista_fondos = []
			lista_agregados = []

			for el in elecs:
				if (el.entrada):
					lista_entradas.append(el.entrada)
					lista_fondos.append(el.fondo)
					lista_agregados.append(el.agregado)

			# Se crear un diccionario para entradas y fondo+agregado, con la cuenta
			cuentas_entradas = {}
			for ent in lista_entradas:
				cuentas_entradas[ent] = lista_entradas.count(ent)
			cuentas_fondos = {}
			for fon in lista_fondos:
				cuentas_fondos[fon] = lista_fondos.count(fon)
			cuentas_agregados = {}
			for agr in lista_agregados:
				cuentas_agregados[agr] = lista_agregados.count(agr)

			chart_ent_val = ','.join('%s' % (k) for k in cuentas_entradas.values())
			chart_ent_eti = '|'.join('%s' % (k) for k in cuentas_entradas.keys())
			chart_fon_val = ','.join('%s' % (k) for k in cuentas_fondos.values())
			chart_fon_eti = '|'.join('%s' % (k) for k in cuentas_fondos.keys())
			chart_agr_val = ','.join('%s' % (k) for k in cuentas_agregados.values())
			chart_agr_eti = '|'.join('%s' % (k) for k in cuentas_agregados.keys())

			elecciones = Eleccion.gql("WHERE usuario = :1 ORDER BY fecha DESC", usuario)
			tmpl_vals = {'url_salir'	: url_salir,
						 'usuario'		: usuario,
						 'elecciones'	: elecciones,
						 'chart_entradas_valor'		:	chart_ent_val,
						 'chart_entradas_etiqueta'	:	chart_ent_eti,
						 'chart_fondos_valor'		:	chart_fon_val,
						 'chart_fondos_etiqueta'	:	chart_fon_eti,
						 'chart_agregados_valor'	:	chart_agr_val,
						 'chart_agregados_etiqueta'	:	chart_agr_eti}
			path = os.path.join(os.path.dirname(__file__), 'tmpl/dieta.html')
			self.response.out.write(template.render(path, tmpl_vals))
		else:
			self.redirect(users.create_login_url(self.request.uri))


application = webapp.WSGIApplication([('/', MainPage), 
									  ('/menu', Almuerzo),
									  ('/pedido', Pedido),
									  ('/resumen', Resumen),
									  ('/midieta', Dieta)], debug=True)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()
