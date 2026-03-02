const API_BASE = '/api';

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }
  return response.json();
}

// Highlights
export const api = {
  // Get highlights with optional filters
  highlights: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJSON(`${API_BASE}/highlights?${query}`);
  },

  // Get a single highlight with annotations
  highlight: (id) => fetchJSON(`${API_BASE}/highlights/${id}`),

  // Create a new highlight
  createHighlight: (data) =>
    fetchJSON(`${API_BASE}/highlights`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Update a highlight
  updateHighlight: (id, data) =>
    fetchJSON(`${API_BASE}/highlights/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // Delete a highlight
  deleteHighlight: (id) =>
    fetchJSON(`${API_BASE}/highlights/${id}`, {
      method: 'DELETE',
    }),

  // Toggle favorite
  toggleFavorite: (id) =>
    fetchJSON(`${API_BASE}/highlights/${id}/favorite`, {
      method: 'POST',
    }),

  // Toggle read status
  toggleRead: (id) =>
    fetchJSON(`${API_BASE}/highlights/${id}/read`, {
      method: 'POST',
    }),

  // Annotations
  getAnnotations: (highlightId) =>
    fetchJSON(`${API_BASE}/highlights/${highlightId}/annotations`),

  createAnnotation: (data) =>
    fetchJSON(`${API_BASE}/annotations`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateAnnotation: (id, data) =>
    fetchJSON(`${API_BASE}/annotations/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteAnnotation: (id) =>
    fetchJSON(`${API_BASE}/annotations/${id}`, {
      method: 'DELETE',
    }),

  // Tags
  getTags: () => fetchJSON(`${API_BASE}/tags`),

  renameTag: (oldName, newName) =>
    fetchJSON(`${API_BASE}/tags/rename?old_name=${encodeURIComponent(oldName)}&new_name=${encodeURIComponent(newName)}`, {
      method: 'POST',
    }),

  deleteTag: (name) =>
    fetchJSON(`${API_BASE}/tags/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    }),

  // Review
  getNextReview: (limit = 20) =>
    fetchJSON(`${API_BASE}/review/next?limit=${limit}`),

  submitReview: (id, quality) =>
    fetchJSON(`${API_BASE}/review/${id}`, {
      method: 'POST',
      body: JSON.stringify({ quality }),
    }),

  // Favorites
  getFavorites: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJSON(`${API_BASE}/favorites?${query}`);
  },

  // Reports
  getReports: (limit = 30) =>
    fetchJSON(`${API_BASE}/reports?limit=${limit}`),

  getReport: (date) =>
    fetchJSON(`${API_BASE}/reports/${date}`),

  generateReport: (date = null, force = false) =>
    fetchJSON(`${API_BASE}/reports`, {
      method: 'POST',
      body: JSON.stringify({ date, force }),
    }),

  // Stats
  getStats: () => fetchJSON(`${API_BASE}/stats`),

  // AI
  summarize: (text) =>
    fetchJSON(`${API_BASE}/ai/summarize`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  suggestTags: (text, existingTags = '') =>
    fetchJSON(`${API_BASE}/ai/suggest-tags`, {
      method: 'POST',
      body: JSON.stringify({ text, existing_tags: existingTags }),
    }),

  // Parser
  parseUrl: (url) =>
    fetchJSON(`${API_BASE}/parse`, {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),

  // Health check
  health: () => fetchJSON(`${API_BASE}/health`),
};

export default api;
