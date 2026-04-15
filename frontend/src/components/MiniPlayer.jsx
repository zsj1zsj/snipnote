import { useLocation, Link } from 'react-router-dom';
import { Play, Pause, SkipBack, SkipForward, X, Headphones } from 'lucide-react';
import { usePlayer } from '../contexts/PlayerContext';

function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function MiniPlayer() {
  const location = useLocation();
  const { episode, isPlaying, currentTime, duration, togglePlay, skip, clearPlayer } = usePlayer();

  // Don't show on the player page itself, or when nothing is loaded
  if (!episode) return null;
  if (location.pathname === `/podcast/episode/${episode.id}`) return null;

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;
  const coverImage = episode.image_url || episode.show_image_url;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-200 shadow-lg">
      {/* Thin progress bar at top */}
      <div className="h-0.5 bg-gray-100">
        <div
          className="h-full bg-blue-500 transition-all duration-1000"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="max-w-5xl mx-auto px-4 py-2 flex items-center gap-3">
        {/* Cover + episode info — click to go back to player */}
        <Link
          to={`/podcast/episode/${episode.id}`}
          className="flex items-center gap-3 flex-1 min-w-0 hover:opacity-80 transition-opacity"
        >
          {coverImage ? (
            <img
              src={coverImage}
              alt={episode.title}
              className="w-10 h-10 rounded-lg object-cover flex-shrink-0"
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          ) : (
            <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
              <Headphones size={18} className="text-gray-400" />
            </div>
          )}
          <div className="min-w-0">
            <div className="text-sm font-medium text-gray-800 truncate">{episode.title}</div>
            <div className="text-xs text-gray-400 truncate">
              {episode.show_title}
              {duration > 0 && ` · ${formatTime(currentTime)} / ${formatTime(duration)}`}
            </div>
          </div>
        </Link>

        {/* Controls */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={() => skip(-15)}
            className="p-2 text-gray-500 hover:text-gray-800 transition-colors"
            title="后退 15 秒"
          >
            <SkipBack size={18} />
          </button>
          <button
            onClick={togglePlay}
            className="w-9 h-9 flex items-center justify-center rounded-full bg-gray-900 text-white hover:bg-gray-700 transition-colors"
          >
            {isPlaying ? <Pause size={16} /> : <Play size={16} className="ml-0.5" />}
          </button>
          <button
            onClick={() => skip(30)}
            className="p-2 text-gray-500 hover:text-gray-800 transition-colors"
            title="前进 30 秒"
          >
            <SkipForward size={18} />
          </button>
          <button
            onClick={clearPlayer}
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors ml-1"
            title="关闭播放器"
          >
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
