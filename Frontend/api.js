// Configuración de la API
const API_BASE_URL = 'http://localhost:5001/api';
const FALLBACK_PORTS = [5001, 5000, 8000, 3000]; // Puertos alternativos para probar

// Clase para manejar las llamadas a la API
class ApiClient {
    constructor() {
        this.baseURL = API_BASE_URL;
        this.token = localStorage.getItem('access_token');
        this.serverDetected = false;
    }

    buildQuery(params = {}) {
        const entries = Object.entries(params || {}).filter(([, value]) => value !== undefined && value !== null && value !== '');
        if (entries.length === 0) return '';
        const query = entries
            .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
            .join('&');
        return `?${query}`;
    }

    // Detectar servidor disponible
    async detectServer() {
        if (this.serverDetected) return true;
        
        console.log('🔍 Detectando servidor disponible...');
        
        for (const port of FALLBACK_PORTS) {
            const testUrl = `http://localhost:${port}/api/test`;
            try {
                console.log(`🌐 Probando puerto ${port}...`);
                const response = await fetch(testUrl, { 
                    method: 'GET',
                    timeout: 3000 // 3 segundos de timeout
                });
                
                if (response.ok) {
                    console.log(`✅ Servidor encontrado en puerto ${port}`);
                    this.baseURL = `http://localhost:${port}/api`;
                    this.serverDetected = true;
                    return true;
                }
            } catch (error) {
                console.log(`❌ Puerto ${port} no disponible`);
            }
        }
        
        console.error('❌ No se pudo conectar con ningún servidor');
        return false;
    }

    // Configurar headers por defecto
    getHeaders() {
        const headers = {
            'Content-Type': 'application/json'
        };
        
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }
        
        return headers;
    }

    // Método genérico para hacer peticiones
    async request(endpoint, options = {}) {
        // Intentar detectar servidor si no se ha hecho
        if (!this.serverDetected) {
            const serverFound = await this.detectServer();
            if (!serverFound) {
                throw new Error('No se pudo conectar con el servidor. Verifica que el backend esté funcionando.');
            }
        }
        
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            headers: this.getHeaders(),
            ...options
        };

        console.log(`🌐 Realizando petición a: ${url}`);
        console.log(`📋 Configuración:`, config);

        try {
            const response = await fetch(url, config);
            console.log(`📡 Respuesta recibida:`, response.status, response.statusText);
            
            const data = await response.json();
            console.log(`📦 Datos recibidos:`, data);
            
            if (!response.ok) {
                // Gestionar expiración de token
                if (response.status === 401 && (data.msg || '').toLowerCase().includes('expired')) {
                    console.warn('🔑 Token expirado, cerrando sesión automáticamente.');
                    this.token = null;
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('user_rol');
                    localStorage.removeItem('user_data');
                    alert('Tu sesión ha expirado. Por favor inicia sesión nuevamente.');
                    window.location.href = 'index.html';
                    return; // Detener flujo
                }
                throw new Error(data.msg || 'Error en la petición');
            }
            
            return data;
        } catch (error) {
            console.error('❌ Error en API:', {
                url: url,
                error: error.message,
                stack: error.stack
            });
            
            // Si hay error de conexión, intentar redetectar servidor
            if (error.message.includes('Failed to fetch')) {
                console.log('🔄 Reintentando detección de servidor...');
                this.serverDetected = false;
                return await this.request(endpoint, options);
            }
            
            // Traducir errores comunes al español
            let errorMessage = error.message;
            if (error.message.includes('Failed to fetch')) {
                errorMessage = 'Error de conexión: No se puede conectar con el servidor. Verifica que el backend esté funcionando.';
            } else if (error.message.includes('Network request failed')) {
                errorMessage = 'Error de red: Verifica tu conexión a internet.';
            } else if (error.message.includes('timeout')) {
                errorMessage = 'Tiempo de espera agotado: El servidor tardó demasiado en responder.';
            }
            
            throw new Error(errorMessage);
        }
    }

    // Métodos de autenticación
    async login(correo, password) {
        const data = await this.request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ correo, password })
        });
        
        if (data.access_token) {
            this.token = data.access_token;
            localStorage.setItem('access_token', this.token);
            localStorage.setItem('user_rol', data.rol);
            localStorage.setItem('user_data', JSON.stringify(data.user));
        }
        
        return data;
    }

    async getProfile() {
        return await this.request('/auth/profile');
    }

    async updateProfile(profileData) {
        return await this.request('/auth/profile', {
            method: 'PUT',
            body: JSON.stringify(profileData)
        });
    }

    logout() {
        this.token = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_rol');
        localStorage.removeItem('user_data');
    }

    // Métodos para convocatorias
    async crearConvocatoria(convocatoria) {
        return await this.request('/convocatorias', {
            method: 'POST',
            body: JSON.stringify(convocatoria)
        });
    }

    async asignarFechas(id, fechas) {
        return await this.request(`/convocatorias/${id}/fechas`, {
            method: 'PATCH',
            body: JSON.stringify(fechas)
        });
    }

    async obtenerConvocatoriasActivas() {
        return await this.request('/convocatorias/activas');
    }

    async obtenerConvocatorias(params = {}) {
        const query = this.buildQuery(params);
        return await this.request(`/convocatorias${query}`);
    }

    async postularConvocatoria(convocatoriaId, payload = {}) {
        return await this.request(`/convocatorias/${convocatoriaId}/postulaciones`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }

    async inscribirseMonitoria(convocatoriaId, payload = {}) {
        return await this.request(`/convocatorias/${convocatoriaId}/inscripciones`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }

    async obtenerPostulaciones(convocatoriaId, params = {}) {
        const query = this.buildQuery(params);
        return await this.request(`/convocatorias/${convocatoriaId}/postulaciones${query}`);
    }

    async obtenerPostulacionesPreasignadas(params = {}) {
        const query = this.buildQuery(params);
        return await this.request(`/postulaciones/preasignadas${query}`);
    }

    async crearPostulacionPreasignada(payload = {}) {
        return await this.request('/postulaciones/preasignadas', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }

    async actualizarPostulacionPreasignada(id, payload = {}) {
        return await this.request(`/postulaciones/preasignadas/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(payload)
        });
    }

    async eliminarPostulacionPreasignada(id) {
        return await this.request(`/postulaciones/preasignadas/${id}`, {
            method: 'DELETE'
        });
    }

    async obtenerOpcionesPreasignadas() {
        return await this.request('/postulaciones/preasignadas/opciones');
    }

    async decidirPostulacion(convocatoriaId, postulacionId, payload = {}) {
        return await this.request(`/convocatorias/${convocatoriaId}/postulaciones/${postulacionId}/decision`, {
            method: 'PATCH',
            body: JSON.stringify(payload)
        });
    }

    async obtenerNotificaciones(params = {}) {
        const query = this.buildQuery(params);
        return await this.request(`/notificaciones${query}`);
    }

    async marcarNotificacionLeida(id) {
        return await this.request(`/notificaciones/${id}/leer`, {
            method: 'POST'
        });
    }

    async marcarTodasNotificacionesLeidas() {
        return await this.request('/notificaciones/marcar-todas', {
            method: 'POST'
        });
    }

    async obtenerConfigIA() {
        return await this.request('/ia/config');
    }

    async actualizarConfigIA(configPayload) {
        return await this.request('/ia/config', {
            method: 'PUT',
            body: JSON.stringify(configPayload)
        });
    }

    async procesarEstados() {
        return await this.request('/convocatorias/process', {
            method: 'POST'
        });
    }

    // Verificar si el usuario está autenticado
    isAuthenticated() {
        return !!this.token;
    }

    getUserRole() {
        return localStorage.getItem('user_rol');
    }

    getUserData() {
        const userData = localStorage.getItem('user_data');
        return userData ? JSON.parse(userData) : null;
    }
}

// Instancia global del cliente API
const apiClient = new ApiClient();

// Funciones de utilidad para el frontend
const ApiUtils = {
    // Mostrar modal de carga
    showLoadingModal() {
        const modal = document.getElementById('loadingModal');
        if (modal) {
            modal.style.display = 'flex';
        }
    },

    // Ocultar modal de carga
    hideLoadingModal() {
        const modal = document.getElementById('loadingModal');
        if (modal) {
            modal.style.display = 'none';
        }
    },

    // Mostrar mensaje de error
    showError(message) {
        alert('Error: ' + message); // Puedes cambiar esto por un modal más elegante
    },

    // Mostrar mensaje de éxito
    showSuccess(message) {
        alert('Éxito: ' + message); // Puedes cambiar esto por un modal más elegante
    },

    // Formatear fechas
    formatDate(dateString) {
        if (!dateString) return 'No asignada';
        const date = new Date(dateString);
        return date.toLocaleString('es-ES');
    },

    // Obtener opciones de semestre
    getSemesterOptions() {
        return [
            { value: '1', label: '1er Semestre' },
            { value: '2', label: '2do Semestre' },
            { value: '3', label: '3er Semestre' },
            { value: '4', label: '4to Semestre' },
            { value: '5', label: '5to Semestre' },
            { value: '6', label: '6to Semestre' },
            { value: '7', label: '7mo Semestre' },
            { value: '8', label: '8vo Semestre' },
            { value: '9', label: '9no Semestre' },
            { value: '10', label: '10mo Semestre' }
        ];
    },

    getUserRole() {
        return apiClient.getUserRole();
    },

    getUserData() {
        return apiClient.getUserData();
    },

    isAuthenticated() {
        if (apiClient.isAuthenticated()) {
            return true;
        }
        const storedToken = localStorage.getItem('access_token');
        if (storedToken) {
            apiClient.token = storedToken;
            return true;
        }
        return false;
    },

    logout() {
        apiClient.logout();
    },

    // Verificar si el usuario es estudiante
    isStudent() {
        return this.getUserRole() === 'STUDENT';
    },

    // Verificar si el usuario es coordinador
    isCoordinator() {
        return this.getUserRole() === 'COORDINATOR';
    },

    // Verificar si el usuario es profesor
    isProfessor() {
        return this.getUserRole() === 'PROFESSOR';
    },

    // Verificar si el usuario puede gestionar convocatorias (coordinador o profesor)
    canManageConvocatorias() {
        return this.isCoordinator() || this.isProfessor();
    },

    // Crear convocatoria
    async createConvocatoria(convocatoriaData) {
        try {
            console.log('📝 Intentando crear convocatoria:', convocatoriaData);
            console.log('🔗 URL del servidor:', apiClient.baseURL);
            console.log('🔑 Token disponible:', !!apiClient.token);
            
            const response = await apiClient.crearConvocatoria(convocatoriaData);
            console.log('✅ Respuesta del servidor:', response);
            return { success: true, data: response };
        } catch (error) {
            console.error('❌ Error detallado al crear convocatoria:', {
                message: error.message,
                stack: error.stack,
                convocatoriaData: convocatoriaData
            });
            
            // Mejorar el mensaje de error
            let errorMessage = error.message;
            if (errorMessage.includes('Failed to fetch') || errorMessage.includes('No se puede conectar')) {
                errorMessage = `Error de conexión con el servidor. 
                
Posibles soluciones:
1. Verifica que el servidor Flask esté ejecutándose en http://localhost:5001
2. Revisa la consola del servidor para errores
3. Verifica que no haya problemas de firewall
4. Intenta refrescar la página`;
            }
            
            return { success: false, error: errorMessage };
        }
    },

    // Listar convocatorias
    async getConvocatorias(params = {}) {
        try {
            const response = await apiClient.obtenerConvocatorias(params);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al obtener convocatorias:', error);
            return { success: false, error: error.message };
        }
    },

    async getConvocatoriasArchivadas() {
        return await this.getConvocatorias({ archivadas: 'solo' });
    },

    async decidirPostulacion(convocatoriaId, postulacionId, decision, comentario = '') {
        try {
            const payload = { decision, comentario };
            const response = await apiClient.decidirPostulacion(convocatoriaId, postulacionId, payload);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al registrar la decisión de la postulación:', error);
            return { success: false, error: error.message };
        }
    },

    async getPostulacionesPreasignadas(params = {}) {
        try {
            const response = await apiClient.obtenerPostulacionesPreasignadas(params);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al obtener preasignaciones:', error);
            return { success: false, error: error.message };
        }
    },

    async crearPostulacionPreasignada(payload = {}) {
        try {
            const response = await apiClient.crearPostulacionPreasignada(payload);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al crear preasignación:', error);
            return { success: false, error: error.message };
        }
    },

    async actualizarPostulacionPreasignada(id, payload = {}) {
        try {
            const response = await apiClient.actualizarPostulacionPreasignada(id, payload);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al actualizar preasignación:', error);
            return { success: false, error: error.message };
        }
    },

    async eliminarPostulacionPreasignada(id) {
        try {
            const response = await apiClient.eliminarPostulacionPreasignada(id);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al eliminar preasignación:', error);
            return { success: false, error: error.message };
        }
    },

    async getPreasignadasOpciones() {
        try {
            const response = await apiClient.obtenerOpcionesPreasignadas();
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al obtener opciones de preasignación:', error);
            return { success: false, error: error.message };
        }
    },

    async getNotificaciones(params = {}) {
        try {
            const response = await apiClient.obtenerNotificaciones(params);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al obtener notificaciones:', error);
            return { success: false, error: error.message };
        }
    },

    async markNotificationRead(id) {
        try {
            const response = await apiClient.marcarNotificacionLeida(id);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al marcar notificación como leída:', error);
            return { success: false, error: error.message };
        }
    },

    async markAllNotificationsRead() {
        try {
            const response = await apiClient.marcarTodasNotificacionesLeidas();
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al marcar todas las notificaciones como leídas:', error);
            return { success: false, error: error.message };
        }
    },

    // Asignar fechas a convocatoria
    async assignFechasConvocatoria(convocatoriaId, fechasData) {
        try {
            const response = await apiClient.asignarFechas(convocatoriaId, fechasData);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al asignar fechas:', error);
            return { success: false, error: error.message };
        }
    },

    // Obtener convocatorias activas
    async getConvocatoriasActivas() {
        try {
            const response = await apiClient.obtenerConvocatoriasActivas();
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al obtener convocatorias activas:', error);
            return { success: false, error: error.message };
        }
    },

    async postularConvocatoria(convocatoriaId, payload = {}) {
        try {
            const response = await apiClient.postularConvocatoria(convocatoriaId, payload);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al postularse:', error);
            return { success: false, error: error.message };
        }
    },

    async inscribirseMonitoria(convocatoriaId, payload = {}) {
        try {
            const response = await apiClient.inscribirseMonitoria(convocatoriaId, payload);
            return { success: true, data: response };
        } catch (error) {
            console.error('Error al inscribirse en la monitoría:', error);
            return { success: false, error: error.message };
        }
    }
};

// Exportar para uso en otros archivos
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { apiClient, ApiUtils };
}

// Inicialización automática para probar conectividad
document.addEventListener('DOMContentLoaded', async function() {
    console.log('🚀 Inicializando conexión con el servidor...');
    try {
        await apiClient.detectServer();
        console.log('✅ Servidor detectado y conectado correctamente');
    } catch (error) {
        console.warn('⚠️ Problema al conectar con el servidor:', error.message);
    }
});