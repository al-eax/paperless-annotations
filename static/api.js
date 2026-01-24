/**
 * API client for managing document annotations.
 */
class ApiClient {
    constructor(docId, showError) {
        this.docId = docId;
        this.baseUrl = `/api/documents/${docId}/annotations`;
        this.showError = showError || console.error;
    }

    /**
     * Internal fetch wrapper with error handling.
     * @private
     */
    async _apiFetch(url, options = {}) {
        options.credentials = options.credentials ?? 'same-origin';

        try {
            const res = await fetch(url, options);
            if (!res.ok) {
                const errorText = await res.text().catch(() => '');
                const message = `Request failed (${res.status})${errorText ? '\n' + errorText : ''}`;
                this.showError(message);
                throw new Error(message);
            }
            return res.json();
        } catch (err) {
            this.showError(err?.message || 'Network error');
            throw err;
        }
    }


    /**
     * Get a cookie value by name.
     * @private
     */
    _getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        return parts.length === 2 ? parts.pop().split(';').shift() : null;
    }

    /**
     * Build common headers for mutating requests.
     * @private
     */
    _buildHeaders() {
        return {
            'Content-Type': 'application/json',
            'X-CSRFToken': this._getCookie('csrftoken'),
        };
    }

    /**
     * Retrieve annotations for a specific page.
     * @param {number} page - The page number
     * @returns {Promise<Array>} List of annotations
     */
    getAnnosForPage(page) {
        return this._apiFetch(`${this.baseUrl}?page=${page}`);
    }

    /**
     * Retrieve all annotations for the document.
     * @returns {Promise<Array>} List of annotations
     */
    getAnnosForDocument() {
        return this._apiFetch(this.baseUrl);
    }

    /**
     * Create a new annotation.
     * @param {Object} annotation - The annotation object
     * @returns {Promise<Object>} Created annotation with db_id
     */
    createAnno(annotation) {
        return this._apiFetch(this.baseUrl, {
            method: 'POST',
            headers: this._buildHeaders(),
            body: JSON.stringify(annotation),
        });
    }

    /**
     * Update an existing annotation.
     * @param {Object} annotation - The annotation object with db_id
     * @returns {Promise<Object>} Updated annotation
     */
    updateAnno(annotation) {
        return this._apiFetch(`${this.baseUrl}/${annotation.db_id}`, {
            method: 'PATCH',
            headers: this._buildHeaders(),
            body: JSON.stringify(annotation),
        });
    }

    /**
     * Delete an annotation.
     * @param {Object} annotation - The annotation object with db_id
     * @returns {Promise<boolean>} Success status
     */
    deleteAnno(annotation) {
        return this._apiFetch(`${this.baseUrl}/${annotation.db_id}`, {
            method: 'DELETE',
            headers: this._buildHeaders(),
            body: JSON.stringify(annotation),
        });
    }
}

/**
 * Factory function to create an API client instance.
 * @param {string|number} docId - The document ID
 * @param {Function} showError - Optional error handler function
 * @returns {ApiClient} API client instance
 */
export default function Api(docId, showError) {
    return new ApiClient(docId, showError);
}