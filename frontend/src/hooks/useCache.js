/**
 * Simple in-memory cache for preserving list data across navigation.
 * Data persists until manual refresh or page reload.
 */

const cache = new Map();

export function getCache(key) {
  return cache.get(key) ?? null;
}

export function setCache(key, value) {
  cache.set(key, value);
}

export function clearCache(key) {
  if (key) {
    cache.delete(key);
  } else {
    cache.clear();
  }
}
