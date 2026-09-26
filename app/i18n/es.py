"""Spanish catalog. Keys are the English source strings used with ``tr()``.

Keep ``{placeholders}`` and ``{{variables}}`` exactly as in the key.
"""

MESSAGES: dict[str, str] = {
    # -- General actions -----------------------------------------------------------
    "OK": "Aceptar",
    "Cancel": "Cancelar",
    "Save": "Guardar",
    "Create": "Crear",
    "Open": "Abrir",
    "Close": "Cerrar",
    "Delete": "Eliminar",
    "Rename": "Renombrar",
    "Duplicate": "Duplicar",
    "Move": "Mover",
    "Copy": "Copiar",
    "Clear": "Limpiar",
    "Remove": "Quitar",
    "Browse…": "Examinar…",
    "Try again": "Reintentar",
    "Format": "Formatear",
    "Send": "Enviar",
    "New": "Nuevo",
    "Error": "Error",
    "Name": "Nombre",
    "Type": "Tipo",
    "Key": "Clave",
    "Value": "Valor",
    "Header": "Encabezado",
    "Variable": "Variable",
    "Location": "Ubicación",
    "Method": "Método",
    "URL": "URL",
    "active": "activo",
    "secret": "secreto",
    "None": "Ninguno",
    "Text": "Texto",
    "More actions": "Más acciones",
    " px": " px",
    " s": " s",

    # -- Top bar / home ------------------------------------------------------------
    "Active environment": "Entorno activo",
    "No environment": "Sin entorno",
    "No environments": "No hay entornos",
    "Manage environments…": "Gestionar entornos…",
    "Command palette (Ctrl+K)": "Paleta de comandos (Ctrl+K)",
    "History (Ctrl+H)": "Historial (Ctrl+H)",
    "Settings": "Ajustes",
    "Settings (Ctrl+,)": "Ajustes (Ctrl+,)",
    "Project settings…": "Ajustes del proyecto…",
    "Reveal api-client folder": "Mostrar la carpeta api-client",
    "Reload from disk": "Recargar desde disco",
    "Open project…": "Abrir proyecto…",
    "Create project…": "Crear proyecto…",
    "Open recent": "Abrir reciente",
    "Close project": "Cerrar proyecto",
    "Test your APIs without the clutter.": "Prueba tus APIs sin complicaciones.",
    "Open Project": "Abrir proyecto",
    "Create Project": "Crear proyecto",
    "RECENT PROJECTS": "PROYECTOS RECIENTES",
    "No recent projects yet. Open a backend folder to get started.":
        "Aún no hay proyectos recientes. Abre la carpeta de un backend para empezar.",
    "Remove from recent projects": "Quitar de proyectos recientes",
    "{path}  (missing)": "{path}  (no encontrado)",
    "Ctrl+O  open project   ·   Ctrl+Shift+O  create project   ·   v{version}":
        "Ctrl+O  abrir proyecto   ·   Ctrl+Shift+O  crear proyecto   ·   v{version}",

    # -- Sidebar -------------------------------------------------------------------
    "New Request": "Nueva petición",
    "New Collection": "Nueva colección",
    "New Environment": "Nuevo entorno",
    "Search requests...": "Buscar peticiones...",
    "COLLECTIONS": "COLECCIONES",
    "New collection (Ctrl+Shift+N)": "Nueva colección (Ctrl+Shift+N)",
    "No collections yet": "Aún no hay colecciones",
    "Group the endpoints of a controller, e.g. Productos → /api/productos.":
        "Agrupa los endpoints de un controlador, p. ej. Productos → /api/productos.",
    "Create collection": "Crear colección",
    "No matching requests": "Ninguna petición coincide",
    "Rename / Edit…": "Renombrar / editar…",
    "Move to…": "Mover a…",
    "Copy as cURL": "Copiar como cURL",

    # -- Tabs & empty states -------------------------------------------------------
    "Close (Ctrl+W)": "Cerrar (Ctrl+W)",
    "Unsaved changes (saving…)": "Cambios sin guardar (guardando…)",
    "New request (Ctrl+N)": "Nueva petición (Ctrl+N)",
    "Close others": "Cerrar las demás",
    "Close all": "Cerrar todas",
    "No requests yet": "Aún no hay peticiones",
    "Create your first request to start testing your API.":
        "Crea tu primera petición para empezar a probar tu API.",
    "Select a request": "Selecciona una petición",
    "Pick an endpoint from the sidebar or press Ctrl + K to search.":
        "Elige un endpoint en la barra lateral o pulsa Ctrl + K para buscar.",
    "New request": "Nueva petición",
    "Command palette": "Paleta de comandos",
    "Send request": "Enviar petición",
    "Focus URL": "Ir a la URL",

    # -- Request editor ------------------------------------------------------------
    "Params": "Parámetros",
    "Headers": "Encabezados",
    "Auth": "Autenticación",
    "Body": "Cuerpo",
    "QUERY PARAMETERS": "PARÁMETROS DE CONSULTA",
    "PATH VARIABLES": "VARIABLES DE RUTA",
    "Path variable": "Variable de ruta",
    "Copy URL": "Copiar URL",
    "Duplicate request": "Duplicar petición",
    "Format JSON body": "Formatear cuerpo JSON",
    "Enter URL, e.g. {{base_url}}/api/productos": "Escribe la URL, p. ej. {{base_url}}/api/productos",
    "no environment": "sin entorno",
    "<b>{name}</b> is not defined in <i>{env}</i>": "<b>{name}</b> no está definida en <i>{env}</i>",
    "Body is not valid JSON — nothing to format": "El cuerpo no es JSON válido: no hay nada que formatear",
    "Request cancelled": "Petición cancelada",
    "The request was cancelled before a response arrived.": "La petición se canceló antes de recibir respuesta.",
    "URL copied to clipboard": "URL copiada al portapapeles",
    "Enable / disable": "Activar / desactivar",
    "Secret: stored in .secrets.json (not committed)": "Secreto: se guarda en .secrets.json (no se sube a Git)",

    # -- Auth ----------------------------------------------------------------------
    "No Auth": "Sin autenticación",
    "Bearer Token": "Bearer Token",
    "Basic Auth": "Basic Auth",
    "Token": "Token",
    "Username": "Usuario",
    "Password": "Contraseña",
    "Username or {{username}}": "Usuario o {{username}}",
    "Password or {{password}}": "Contraseña o {{password}}",
    "Show password": "Mostrar contraseña",
    "This request does not send authentication.": "Esta petición no envía autenticación.",
    "Choose Bearer Token or Basic Auth above to add an Authorization header.":
        "Elige Bearer Token o Basic Auth arriba para añadir un encabezado Authorization.",
    "Sent as  Authorization: Bearer <token>.  Keep real tokens in .secrets.json and reference them as {{token}}.":
        "Se envía como  Authorization: Bearer <token>.  Guarda los tokens reales en .secrets.json y "
        "referéncialos como {{token}}.",
    "Sent as  Authorization: Basic base64(username:password).":
        "Se envía como  Authorization: Basic base64(usuario:contraseña).",

    # -- Body ----------------------------------------------------------------------
    "Content": "Contenido",
    "Format JSON (Ctrl+Shift+F)": "Formatear JSON (Ctrl+Shift+F)",
    "This request has no body": "Esta petición no tiene cuerpo",
    "Select JSON or Text above to send a request body.": "Elige JSON o Texto arriba para enviar un cuerpo.",
    "Valid JSON": "JSON válido",
    "Invalid JSON — line {line}: {message}": "JSON inválido — línea {line}: {message}",
    "Invalid JSON: {message}": "JSON inválido: {message}",

    # -- Response viewer -----------------------------------------------------------
    "Press": "Pulsa",
    "to send": "para enviar",
    "Send a request to see the response here.": "Envía una petición para ver aquí la respuesta.",
    "Sending request…": "Enviando petición…",
    "Raw": "Sin formato",
    "Copy response body": "Copiar el cuerpo de la respuesta",
    "Toggle word wrap": "Ajuste de línea",
    "Find (Ctrl+F)": "Buscar (Ctrl+F)",
    "Find in response": "Buscar en la respuesta",
    "Next (Enter)": "Siguiente (Enter)",
    "Close (Esc)": "Cerrar (Esc)",
    "No results": "Sin resultados",
    "Copy body": "Copiar cuerpo",
    "Copy headers": "Copiar encabezados",
    "Copy raw response": "Copiar respuesta sin formato",
    "Save body to file…": "Guardar cuerpo en un archivo…",
    "Body: {size}\nHeaders included in total": "Cuerpo: {size}\nEl total incluye los encabezados",
    "Body truncated (over 50 MB)": "Cuerpo truncado (más de 50 MB)",
    "No response body": "La respuesta no tiene cuerpo",
    "HEAD responses have no body": "Las respuestas HEAD no tienen cuerpo",
    "Binary content ({type}, {size}).\nUse More → Save body to file to inspect it.":
        "Contenido binario ({type}, {size}).\nUsa Más → Guardar cuerpo en un archivo para inspeccionarlo.",
    "unknown type": "tipo desconocido",
    "RESPONSE HEADERS": "ENCABEZADOS DE RESPUESTA",
    "REQUEST": "PETICIÓN",
    "HTTP version": "Versión HTTP",
    "Response body copied to clipboard": "Cuerpo de la respuesta copiado al portapapeles",
    "Headers copied to clipboard": "Encabezados copiados al portapapeles",
    "Raw response copied to clipboard": "Respuesta sin formato copiada al portapapeles",
    "Save response body": "Guardar cuerpo de la respuesta",
    "Response saved": "Respuesta guardada",

    # -- Network errors ------------------------------------------------------------
    "Request timed out": "Tiempo de espera agotado",
    "No answer after {seconds} s while {phase}\n{origin}": "Sin respuesta tras {seconds} s al {phase}\n{origin}",
    "connecting to": "conectar con",
    "waiting for a response from": "esperar la respuesta de",
    "sending data to": "enviar datos a",
    "waiting for a free connection to": "esperar una conexión libre con",
    "talking to": "comunicarse con",
    "The server may be busy or stuck. You can raise the timeout in Settings → Network.":
        "El servidor puede estar ocupado o bloqueado. Puedes aumentar el tiempo de espera en Ajustes → Red.",
    "Too many redirects": "Demasiadas redirecciones",
    "The server kept redirecting the request.\n{url}": "El servidor redirigió la petición una y otra vez.\n{url}",
    "Check for a redirect loop, or disable 'Follow redirects' in Settings → Network.":
        "Revisa si hay un bucle de redirecciones o desactiva 'Seguir redirecciones' en Ajustes → Red.",
    "Invalid URL": "URL inválida",
    "URLs must start with http:// or https:// and include a host, e.g. http://localhost:8080/api.":
        "La URL debe empezar por http:// o https:// e incluir un host, p. ej. http://localhost:8080/api.",
    "SSL error": "Error de SSL",
    "Secure connection to {origin} failed.": "Falló la conexión segura con {origin}.",
    "The certificate may be self-signed or expired. For local development you can disable SSL verification in "
    "Settings → Network.":
        "El certificado puede ser autofirmado o estar caducado. En desarrollo local puedes desactivar la "
        "verificación SSL en Ajustes → Red.",
    "Host not found": "Host no encontrado",
    "Could not resolve the host name:\n{host}": "No se pudo resolver el nombre del host:\n{host}",
    "Check the URL for typos and verify your network or VPN connection.":
        "Revisa que la URL esté bien escrita y comprueba tu conexión de red o VPN.",
    "Connection refused": "Conexión rechazada",
    "Could not connect to:\n{origin}": "No se pudo conectar con:\n{origin}",
    "Make sure the server is running and listening on that port.":
        "Verifica que el servidor esté en ejecución y escuchando en ese puerto.",
    "Protocol error": "Error de protocolo",
    "The server response could not be understood.": "No se pudo interpretar la respuesta del servidor.",
    "The server may have closed the connection unexpectedly or is not speaking HTTP on this port.":
        "Puede que el servidor haya cerrado la conexión inesperadamente o que no use HTTP en este puerto.",
    "Network error": "Error de red",
    "The request to {origin} failed.": "Falló la petición a {origin}.",
    "Check your network connection and that the server is reachable.":
        "Comprueba tu conexión de red y que el servidor sea accesible.",
    "Unexpected error": "Error inesperado",

    # -- Request building ----------------------------------------------------------
    "Circular variable": "Variable circular",
    "Circular variable reference: {chain}": "Referencia circular entre variables: {chain}",
    "Make sure variables do not reference each other in a loop.":
        "Asegúrate de que las variables no se referencien entre sí en bucle.",
    "Missing variable": "Variable no definida",
    "Variable not defined: {names}": "Variable no definida: {names}",
    "Variables not defined: {names}": "Variables no definidas: {names}",
    'Variable not defined in environment "{env}": {names}': 'Variable no definida en el entorno "{env}": {names}',
    'Variables not defined in environment "{env}": {names}': 'Variables no definidas en el entorno "{env}": {names}',
    'Define it in the "{env}" environment (Environments) or in api-client/.secrets.json.':
        'Defínela en el entorno "{env}" (Entornos) o en api-client/.secrets.json.',
    "Define it in the current environment (Environments) or in api-client/.secrets.json.":
        "Defínela en el entorno actual (Entornos) o en api-client/.secrets.json.",
    "Authentication incomplete": "Autenticación incompleta",
    "Bearer token is empty. Set it in the Auth tab or disable authentication.":
        "El Bearer token está vacío. Complétalo en la pestaña Autenticación o desactiva la autenticación.",
    "Basic Auth username is empty.": "El usuario de Basic Auth está vacío.",
    "URL is empty": "La URL está vacía",
    "Enter the URL of the endpoint to call.": "Escribe la URL del endpoint que quieres llamar.",
    "Example: {{base_url}}/api/productos": "Ejemplo: {{base_url}}/api/productos",
    "Example: http://localhost:8080/api/productos": "Ejemplo: http://localhost:8080/api/productos",
    "Unsupported URL scheme": "Esquema de URL no soportado",
    '"{scheme}" is not supported. Use http:// or https://.': '"{scheme}" no está soportado. Usa http:// o https://.',
    "The URL has no host:\n{url}": "La URL no tiene host:\n{url}",
    "Missing path parameter": "Falta un parámetro de ruta",
    "The path parameter {param} has no value.": "El parámetro de ruta {param} no tiene valor.",
    "Fill it in the Params tab under Path Variables.":
        "Complétalo en la pestaña Parámetros, en Variables de ruta.",
    "Invalid JSON body": "Cuerpo JSON inválido",
    "Line {line}, column {column}: {message}": "Línea {line}, columna {column}: {message}",
    "Fix the body before sending (Ctrl+Shift+F formats valid JSON).":
        "Corrige el cuerpo antes de enviar (Ctrl+Shift+F formatea el JSON válido).",

    # Messages produced by Python's json module (see json_service.translate_json_error)
    "Expecting value": "Se esperaba un valor",
    "Expecting ',' delimiter": "Se esperaba el separador ','",
    "Expecting ':' delimiter": "Se esperaba el separador ':'",
    "Expecting property name enclosed in double quotes": "Se esperaba un nombre de propiedad entre comillas dobles",
    "Unterminated string starting at": "Cadena sin cerrar que empieza en",
    "Invalid control character at": "Carácter de control inválido en",
    "Invalid \\escape": "Secuencia de escape inválida",
    "Invalid \\uXXXX escape": "Escape \\uXXXX inválido",
    "Extra data": "Datos sobrantes",
    "Illegal trailing comma before end of object": "Coma sobrante antes del final del objeto",
    "Illegal trailing comma before end of array": "Coma sobrante antes del final del array",

    # -- Dialogs: base, confirm ----------------------------------------------------
    "Quit without saving?": "¿Salir sin guardar?",
    "Some changes could not be written to disk.": "Algunos cambios no se pudieron escribir en disco.",
    "Quit anyway": "Salir de todos modos",

    # -- Project dialogs -----------------------------------------------------------
    "Create API Client Project": "Crear proyecto de API Client",
    "Project name": "Nombre del proyecto",
    "Backend folder": "Carpeta del backend",
    "Base URL": "URL base",
    "Available in requests as {{base_url}}. You can add more environments (dev, production…) later.":
        "Disponible en las peticiones como {{base_url}}. Más adelante puedes añadir otros entornos "
        "(dev, producción…).",
    "Select the backend project folder": "Selecciona la carpeta del proyecto backend",
    "A project already exists in {path}. It will be opened instead.": "Ya existe un proyecto en {path}. Se abrirá ese.",
    "Will create {path}/ with project.json, .secrets.json and .gitignore":
        "Se creará {path}/ con project.json, .secrets.json y .gitignore",
    "Choose an existing folder (the root of your backend project).":
        "Elige una carpeta existente (la raíz de tu proyecto backend).",
    "Enter a project name.": "Escribe un nombre para el proyecto.",
    "The base URL should start with http:// or https://": "La URL base debe empezar por http:// o https://",
    "Project settings": "Ajustes del proyecto",
    "Default base URL": "URL base por defecto",
    "Used as {{base_url}} when the active environment does not define its own.":
        "Se usa como {{base_url}} cuando el entorno activo no define la suya.",

    # -- Request / collection dialogs ----------------------------------------------
    "+ New collection…": "+ Nueva colección…",
    "General": "General",
    "Collection name, e.g. Productos": "Nombre de la colección, p. ej. Productos",
    "Method and collection": "Método y colección",
    "New collection name": "Nombre de la nueva colección",
    "Use {id}-style placeholders for path variables, e.g. {{base_url}}/api/productos/{id}":
        "Usa marcadores como {id} para las variables de ruta, p. ej. {{base_url}}/api/productos/{id}",
    "Edit Collection": "Editar colección",
    "Base path (optional)": "Ruta base (opcional)",
    "Mirrors @RequestMapping on the controller. New requests start with {{base_url}} + this path.":
        "Corresponde al @RequestMapping del controlador. Las peticiones nuevas empiezan con {{base_url}} + esta ruta.",

    # -- Environments dialog -------------------------------------------------------
    "Environments": "Entornos",
    "ENVIRONMENTS": "ENTORNOS",
    "Globals": "Globales",
    "Add environment": "Añadir entorno",
    "Rename environment": "Renombrar entorno",
    "Duplicate environment": "Duplicar entorno",
    "New environment": "Nuevo entorno",
    "Environment name": "Nombre del entorno",
    "Delete environment?": "¿Eliminar el entorno?",
    "Shared by every environment.": "Compartidas por todos los entornos.",
    "Active when “{env}” is selected in the top bar.": "Activas cuando “{env}” está seleccionado en la barra superior.",
    "“{env}” and its variables (including secrets) will be removed when you save.":
        "“{env}” y sus variables (incluidos los secretos) se eliminarán al guardar.",
    "Lock a variable to store it in api-client/.secrets.json, which is git-ignored and never shared. "
    "Environment values override globals.":
        "Bloquea una variable para guardarla en api-client/.secrets.json, que Git ignora y nunca se comparte. "
        "Los valores del entorno tienen prioridad sobre los globales.",

    # -- Settings dialog -----------------------------------------------------------
    "Appearance": "Apariencia",
    "Network": "Red",
    "Open last project on startup": "Abrir el último proyecto al iniciar",
    "Autosave": "Guardado automático",
    "Save request changes automatically while you type.": "Guarda los cambios de las peticiones mientras escribes.",
    "Recent projects shown": "Proyectos recientes mostrados",
    "History entries kept per project": "Entradas de historial por proyecto",
    "Theme": "Tema",
    "Dark": "Oscuro",
    "Light": "Claro",
    "System": "Sistema",
    "Editor font size": "Tamaño de fuente del editor",
    "Body and response editors.": "Editores del cuerpo y de la respuesta.",
    "Timeout": "Tiempo de espera",
    "Maximum time to wait for the server.": "Tiempo máximo de espera al servidor.",
    "Verify SSL certificates": "Verificar certificados SSL",
    "Disable only for local self-signed certificates.": "Desactívalo solo para certificados locales autofirmados.",
    "Follow redirects": "Seguir redirecciones",
    "Language": "Idioma",
    "Interface language.": "Idioma de la interfaz.",
    "System default": "Idioma del sistema",
    "Restart required": "Es necesario reiniciar",
    "The new language will be applied after restarting API Client.":
        "El nuevo idioma se aplicará al reiniciar API Client.",
    "Restart now": "Reiniciar ahora",
    "Later": "Más tarde",

    # -- History dialog ------------------------------------------------------------
    "History": "Historial",
    "Filter by URL, method, status or request name…": "Filtrar por URL, método, estado o nombre de la petición…",
    "TIME": "HORA",
    "METHOD": "MÉTODO",
    "STATUS": "ESTADO",
    "DURATION": "DURACIÓN",
    "SIZE": "TAMAÑO",
    "%b %d  %H:%M:%S": "%d/%m  %H:%M:%S",
    "No requests sent yet": "Aún no se ha enviado ninguna petición",
    "Double-click an entry to open its request. Response bodies are not stored.":
        "Haz doble clic en una entrada para abrir su petición. Los cuerpos de respuesta no se guardan.",
    "Clear history": "Limpiar historial",
    "Clear history?": "¿Limpiar el historial?",
    "All history entries of this project will be removed.": "Se eliminarán todas las entradas del historial de este proyecto.",

    # -- Command palette -----------------------------------------------------------
    "Search requests and actions…": "Buscar peticiones y acciones…",
    "Switch Environment": "Cambiar de entorno",
    "Switch environment…": "Cambiar de entorno…",
    "Manage Environments": "Gestionar entornos",
    "Format JSON": "Formatear JSON",
    "Open History": "Abrir historial",
    "Project Settings": "Ajustes del proyecto",
    "Reload Project from Disk": "Recargar proyecto desde disco",
    "Close Project": "Cerrar proyecto",

    # -- Main window messages ------------------------------------------------------
    "Open backend project folder": "Abrir la carpeta del proyecto backend",
    "Folder not found": "Carpeta no encontrada",
    "{path} does not exist anymore.": "{path} ya no existe.",
    "No API Client configuration": "Sin configuración de API Client",
    "This folder has no api-client/project.json:\n{path}\n\nDo you want to create it?":
        "No existe configuración de API Client en este proyecto (api-client/project.json):\n{path}\n\n"
        "¿Deseas crearla?",
    "Could not create project": "No se pudo crear el proyecto",
    "Writing to {path} failed: {error}.": "No se pudo escribir en {path}: {error}.",
    "Project created": "Proyecto creado",
    "Could not open project": "No se pudo abrir el proyecto",
    "Fix the file (it is plain JSON) or restore it from Git, then try again.":
        "Corrige el archivo (es JSON plano) o restáuralo desde Git y vuelve a intentarlo.",
    "Some files could not be loaded": "Algunos archivos no se pudieron cargar",
    "These files are invalid and were skipped. They have not been modified; fix them and use Reload from disk.":
        "Estos archivos son inválidos y se omitieron. No se han modificado; corrígelos y usa Recargar desde disco.",
    "These files were skipped:": "Se omitieron estos archivos:",
    "Project saved": "Proyecto guardado",
    "Could not reload project": "No se pudo recargar el proyecto",
    "Project reloaded": "Proyecto recargado",
    "Environments saved": "Entornos guardados",
    "That request no longer exists": "Esa petición ya no existe",
    "JSON formatted": "JSON formateado",
    "Editing…": "Editando…",
    "Saving…": "Guardando…",
    "Saved": "Guardado",
    "All changes saved": "Todos los cambios guardados",
    "Unsaved changes — Ctrl+S to save": "Cambios sin guardar — Ctrl+S para guardar",
    "Save failed": "Error al guardar",
    "Could not save changes": "No se pudieron guardar los cambios",
    "Your edits are kept in memory. Check the file permissions and press Ctrl+S to retry.":
        "Tus cambios se mantienen en memoria. Revisa los permisos del archivo y pulsa Ctrl+S para reintentar.",
    "Could not write to disk": "No se pudo escribir en disco",
    "Could not create request": "No se pudo crear la petición",
    "Collection “{name}” created": "Colección “{name}” creada",
    "Collection saved": "Colección guardada",
    "Collection duplicated": "Colección duplicada",
    "Delete collection?": "¿Eliminar la colección?",
    "“{name}” will be permanently removed ({file} is deleted).":
        "“{name}” se eliminará de forma permanente (se borra {file}).",
    "“{name}” and its {n} request will be permanently removed ({file} is deleted).":
        "“{name}” y su {n} petición se eliminarán de forma permanente (se borra {file}).",
    "“{name}” and its {n} requests will be permanently removed ({file} is deleted).":
        "“{name}” y sus {n} peticiones se eliminarán de forma permanente (se borra {file}).",
    "Collection deleted": "Colección eliminada",
    "Rename request": "Renombrar petición",
    "Request duplicated": "Petición duplicada",
    "Move request": "Mover petición",
    "Move “{name}” to": "Mover “{name}” a",
    "Request moved": "Petición movida",
    "Delete request?": "¿Eliminar la petición?",
    "“{name}” will be permanently removed.": "“{name}” se eliminará de forma permanente.",
    "Request deleted": "Petición eliminada",
    "Cannot build cURL command": "No se puede generar el comando cURL",
    "This request contains credentials": "Esta petición contiene credenciales",
    "The command includes an Authorization header or secret variables. Copy it with the values masked "
    "(safe to share), or include them?":
        "El comando incluye un encabezado Authorization o variables secretas. ¿Copiarlo con los valores "
        "ocultos (seguro para compartir) o incluirlos?",
    "Include secrets": "Incluir secretos",
    "Copy masked": "Copiar ocultos",
    "cURL copied": "cURL copiado",
    "cURL copied (secrets masked)": "cURL copiado (secretos ocultos)",
    "Settings saved": "Ajustes guardados",
    "{n} collection": "{n} colección",
    "{n} collections": "{n} colecciones",
    "{n} request": "{n} petición",
    "{n} requests": "{n} peticiones",

    # -- Relative times ------------------------------------------------------------
    "just now": "ahora mismo",
    "{n} min ago": "hace {n} min",
    "{n} h ago": "hace {n} h",
    "yesterday": "ayer",
    "{n} days ago": "hace {n} días",
    "%b %d, %Y": "%d/%m/%Y",

    # -- Object view -----------------------------------------------------------------
    "Object view": "Vista objeto",
    "Show the JSON body as an object tree": "Muestra el cuerpo JSON como un árbol de objetos",
    "Object": "Objeto",
    "Array": "Arreglo",
    "(value)": "(valor)",
    "Collapse all": "Contraer todo",
    "Expand all": "Expandir todo",
    "Copy value as JSON": "Copiar el valor como JSON",
    "Copy selected value as JSON": "Copiar el valor seleccionado como JSON",
    "Value copied to clipboard": "Valor copiado al portapapeles",
    "Copy value": "Copiar valor",
    "Copy key": "Copiar clave",
    "Copy path": "Copiar ruta",
    "Nothing to show yet": "Aún no hay nada que mostrar",
    "Write valid JSON to see its structure": "Escribe un JSON válido para ver su estructura",
    "Invalid JSON — showing the last valid version; navigation is paused":
        "JSON inválido — se muestra la última versión válida; la navegación está en pausa",
    "Path: {path}\nType: {type}": "Ruta: {path}\nTipo: {type}",
    "(root)": "(raíz)",
    "string": "texto",
    "number": "número",
    "boolean": "booleano",
    "null": "nulo",
    "object": "objeto",
    "array": "arreglo",
    "variable": "variable",
    "(too large to show everything)": "(demasiado grande para mostrarlo todo)",
    "{n} field": "{n} campo",
    "{n} fields": "{n} campos",
    "{n} item": "{n} elemento",
    "{n} items": "{n} elementos",
}
