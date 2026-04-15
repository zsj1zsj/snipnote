/**
 * Global podcast player context.
 * A single Audio object lives at module level so playback persists across navigation.
 */
import { createContext, useContext, useState, useEffect, useRef } from 'react';
import api from '../api';
import { getCache, setCache } from '../hooks/useCache';

const PlayerContext = createContext(null);

// Module-level audio singleton — survives re-renders and route changes
const audio = new Audio();
audio.preload = 'metadata';

export function PlayerProvider({ children }) {
  const [episode, setEpisode] = useState(null);   // full episode object
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRateState] = useState(1);

  const progressTimerRef = useRef(null);
  const episodeIdRef = useRef(null);

  // Wire up audio events once
  useEffect(() => {
    const onTimeUpdate = () => {
      setCurrentTime(audio.currentTime);
      // Save progress every 10 seconds
      if (progressTimerRef.current) return;
      progressTimerRef.current = setTimeout(() => {
        progressTimerRef.current = null;
        const pos = Math.floor(audio.currentTime);
        const epId = episodeIdRef.current;
        if (pos > 0 && epId) {
          api.updatePlayProgress(epId, pos).catch(() => {});
          // Update cache
          const cacheKey = `podcast_episode_${epId}`;
          const c = getCache(cacheKey);
          if (c?.episode) { c.episode.play_position = pos; setCache(cacheKey, c); }
        }
      }, 10000);
    };

    const onDurationChange = () => setDuration(audio.duration || 0);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onEnded = () => {
      setIsPlaying(false);
      const epId = episodeIdRef.current;
      if (!epId) return;
      api.toggleEpisodeListened(epId).then((result) => {
        setEpisode(prev => prev ? { ...prev, is_listened: result.is_listened } : prev);
        // Sync caches
        const cacheKey = `podcast_episode_${epId}`;
        const c = getCache(cacheKey);
        if (c?.episode) { c.episode.is_listened = 1; setCache(cacheKey, c); }
        const listCache = getCache('podcast_episodes');
        if (listCache?.episodes) {
          listCache.episodes = listCache.episodes.map(ep =>
            ep.id === epId ? { ...ep, is_listened: 1 } : ep
          );
          setCache('podcast_episodes', listCache);
        }
      }).catch(() => {});
    };

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('durationchange', onDurationChange);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('ended', onEnded);

    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('durationchange', onDurationChange);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('ended', onEnded);
    };
  }, []);

  const loadEpisode = (ep, startTime = 0) => {
    if (episodeIdRef.current === ep.id && audio.src) {
      // Same episode already loaded — just seek if needed
      if (startTime > 0 && Math.abs(audio.currentTime - startTime) > 2) {
        audio.currentTime = startTime;
      }
      return;
    }
    audio.src = ep.audio_url;
    episodeIdRef.current = ep.id;
    setEpisode(ep);
    setCurrentTime(0);
    setDuration(0);

    const onCanPlay = () => {
      if (startTime > 0) audio.currentTime = startTime;
      audio.removeEventListener('canplay', onCanPlay);
    };
    audio.addEventListener('canplay', onCanPlay);
  };

  const togglePlay = () => {
    if (audio.paused) audio.play().catch(() => {});
    else audio.pause();
  };

  const seek = (time) => {
    audio.currentTime = Math.max(0, Math.min(time, audio.duration || 0));
  };

  const skip = (delta) => {
    seek(audio.currentTime + delta);
  };

  const setRate = (r) => {
    audio.playbackRate = r;
    setRateState(r);
  };

  const clearPlayer = () => {
    audio.pause();
    audio.src = '';
    episodeIdRef.current = null;
    setEpisode(null);
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
  };

  return (
    <PlayerContext.Provider value={{
      episode, isPlaying, currentTime, duration, rate,
      loadEpisode, togglePlay, seek, skip, setRate, clearPlayer,
    }}>
      {children}
    </PlayerContext.Provider>
  );
}

export function usePlayer() {
  return useContext(PlayerContext);
}
