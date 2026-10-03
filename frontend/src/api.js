const BASE_URL = '/api';

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function queryString(values) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  return params.toString();
}

export const getDashboard = () => request('/dashboard');
export const getCustomers = () => request('/customers');
export const getCustomer = (customerId) => request(`/customers/${encodeURIComponent(customerId)}`);
export const getTrends = (scope) => request(`/trends?${queryString({ scope })}`);
export const getTransactions = (params) => request(`/transactions?${queryString(params)}`);
export const getLoans = () => request('/loans');
export const getCases = (params) => request(`/cases?${queryString(params)}`);
export const updateCase = (caseId, patch) => request(`/cases/${caseId}`, { method: 'PATCH', body: JSON.stringify(patch) });