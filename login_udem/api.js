// Configuración de la API
const API_BASE_URL = 'http://localhost:5000/api';

// Clase para manejar las llamadas a la API
class ApiClient {
    constructor() {
        this.baseURL = API_BASE_URL;
        this.token = localStorage.getItem('access_token');
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
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            headers: this.getHeaders(),
            ...options
        };

        try {
            const response = await fetch(url, config);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.msg || 'Error en la petición');
            }
            
            return data;
        } catch (error) {
            console.error('Error en API:', error);
            
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

    // Verificar si el usuario es estudiante
    isStudent() {
        return this.getUserRole() === 'STUDENT';
    },

    // Verificar si el usuario es coordinador
    isCoordinator() {
        return this.getUserRole() === 'COORDINATOR';
    }
};

// Exportar para uso en otros archivos
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { apiClient, ApiUtils };
}