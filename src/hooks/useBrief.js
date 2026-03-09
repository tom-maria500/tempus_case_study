import { useState, useCallback, useRef } from 'react';
import { generateBrief } from '../lib/api';

export function useBrief() {
  const [brief, setBrief] = useState(null);
  const [currentPhysicianId, setCurrentPhysicianId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const cacheRef = useRef(new Map());

  const fetchBrief = useCallback(async (physician) => {
    const id = physician?.physician_id;
    if (!id) return;

    const cached = cacheRef.current.get(id);
    if (cached) {
      setBrief(cached.brief);
      setError(cached.error || null);
      setCurrentPhysicianId(id);
      return;
    }

    setCurrentPhysicianId(id);
    setIsLoading(true);
    setError(null);
    try {
      const data = await generateBrief(physician);
      setBrief(data);
      cacheRef.current.set(id, { brief: data, error: null });
    } catch (err) {
      const msg = err.message || 'Failed to generate brief';
      setError(msg);
      setBrief(null);
      cacheRef.current.set(id, { brief: null, error: msg });
    } finally {
      setIsLoading(false);
    }
  }, []);

  const invalidateBrief = useCallback((physicianId) => {
    if (physicianId) {
      cacheRef.current.delete(physicianId);
      if (currentPhysicianId === physicianId) {
        setBrief(null);
        setError(null);
      }
    }
  }, [currentPhysicianId]);

  const clearBrief = useCallback(() => {
    setBrief(null);
    setError(null);
    setCurrentPhysicianId(null);
  }, []);

  const refetchBrief = useCallback(async (physician) => {
    const id = physician?.physician_id;
    if (id) cacheRef.current.delete(id);
    await fetchBrief(physician);
  }, [fetchBrief]);

  return {
    brief,
    isLoading,
    error,
    fetchBrief,
    clearBrief,
    invalidateBrief,
    refetchBrief
  };
}
