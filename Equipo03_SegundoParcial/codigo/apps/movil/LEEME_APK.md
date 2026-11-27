# app-debug.apk

Variante debug de la aplicacion Android del colaborador. Habla JSON con
los microservicios. El archivo esta en esta misma carpeta.

## Como se prueba

Con el sistema corriendo en la misma computadora (`docker compose up -d`),
instalar el APK en un emulador de Android de esa maquina. La cuenta de
demostracion es `ana.perez@nexum.com.mx` con contrasena `demo123`.

## Por que no funciona en un telefono cualquiera

El APK apunta a `http://10.0.2.2:8101`–`8106`. `10.0.2.2` es la forma en
que el emulador ve el `127.0.0.1` de la computadora anfitriona. Fuera del
emulador esa direccion no lleva a los servicios.

El proxy de la nube publica solo el portal (`34.41.26.94.sslip.io` hacia
`127.0.0.1:8000`). Los veinticuatro microservicios no se exponen a internet,
igual que el puerto de la base.
