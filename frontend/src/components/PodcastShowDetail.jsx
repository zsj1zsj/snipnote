import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Headphones, RefreshCw, Loader, CheckCircle, Circle, Play } from 'lucide-react';
import api from '../api';
import { usePlayer } from '../contexts/PlayerContext';
import { getCache, setCache } from '../hooks/useCache';

function formatDuration(seconds) {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export default function PodcastShowDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { loadEpisode, togglePlay, episode: currentEpisode, isPlaying } = usePlayer();
  const cacheKey = `podcast_show_${id}`;

  const [data, setData] = useState(() => getCache(cacheKey) || null);
  const [loading, setLoading] = useState(!getCache(cacheKey));
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all'); // all | unlistened

  const loadData = async () => {
    try {
      const result = await api.getPodcastShow(id);
      setData(result);
      setCache(cacheKey, result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!getCache(cacheKey)) loadData();
  }, [id]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await api.refreshPodcast(parseInt(id));
      const result = await api.getPodcastShow(id);
      setData(result);
      setCache(cacheKey, result);
    } catch (err) {
      setError(err.message);
    } finally {
      setRefreshing(false);
    }
  };

  const handlePlay = (ep) => {
    if (currentEpisode?.id === ep.id) {
      togglePlay();
    } else {
      loadEpisode(ep, ep.play_position || 0);
      togglePlay();
      navigate(`/podcast/episode/${ep.id}`);
    }
  };

  if (loading) {
    return (
      <div className="page-container flex items-center justify-center py-20">
        <Loader size={24} className="animate-spin text-gray-400" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="page-container">
        <div className="text-red-500 text-sm">{error || '加载失败'}</div>
      </div>
    );
  }

  const { episodes = [], ...show } = data;

  // Group episodes by season
  const filtered = filter === 'unlistened' ? episodes.filter(ep => !ep.is_listened) : episodes;
  const seasons = {};
  filtered.forEach(ep => {
    const season = ep.season || 0;
    if (!seasons[season]) seasons[season] = [];
    seasons[season].push(ep);
  });
  const seasonKeys = Object.keys(seasons).map(Number).sort((a, b) => b - a);

  return (
    <div className="page-container max-w-3xl">
      {/* Back button */}
      <button
        onClick={() => navigate('/podcast')}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft size={16} />
        返回订阅列表
      </button>

      {/* Show header */}
      <div className="card p-5 mb-6 flex gap-4">
        {show.image_url ? (
          <img
            src={show.image_url}
            alt={show.title}
            className="w-24 h-24 rounded-xl object-cover flex-shrink-0"
            onError={(e) => { e.target.style.display = 'none'; }}
          />
        ) : (
          <div className="w-24 h-24 rounded-xl bg-gray-100 flex items-center justify-center flex-shrink-0">
            <Headphones size={32} className="text-gray-400" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-semibold text-gray-900 mb-1">{show.title}</h1>
          {show.author && <div className="text-sm text-gray-500 mb-2">{show.author}</div>}
          <div className="text-xs text-gray-400 mb-3">
            {show.total} 集 · {show.unlistened} 集未听
            {show.last_fetched_at && ` · 最后刷新 ${show.last_fetched_at.split('T')[0]}`}
          </div>
          {show.description && (
            <p className="text-sm text-gray-600 line-clamp-3">{show.description}</p>
          )}
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-2">
          <button
            onClick={() => setFilter('all')}
            className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${filter === 'all' ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
          >
            全部 ({episodes.length})
          </button>
          <button
            onClick={() => setFilter('unlistened')}
            className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${filter === 'unlistened' ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
          >
            未听 ({episodes.filter(ep => !ep.is_listened).length})
          </button>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="btn btn-secondary flex items-center gap-2 text-sm"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="card p-8 text-center text-gray-400 text-sm">
          <Headphones size={32} className="mx-auto mb-3 text-gray-300" />
          {filter === 'unlistened' ? '没有未听的单集' : '暂无单集'}
        </div>
      ) : (
        <div className="space-y-6">
          {seasonKeys.map(season => (
            <div key={season}>
              {season > 0 && (
                <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-1">
                  第 {season} 季
                </div>
              )}
              <div className="card divide-y divide-gray-50">
                {seasons[season].map(ep => (
                  <div key={ep.id} className="p-3 flex items-start gap-3">
                    <button
                      onClick={() => handlePlay(ep)}
                      className="mt-0.5 flex-shrink-0 w-8 h-8 rounded-full bg-gray-100 hover:bg-gray-900 hover:text-white text-gray-500 flex items-center justify-center transition-colors"
                    >
                      <Play size={14} className="ml-0.5" />
                    </button>
                    <div className="flex-1 min-w-0">
                      <Link
                        to={`/podcast/episode/${ep.id}`}
                        className="text-sm font-medium text-gray-800 hover:text-gray-600 line-clamp-2 block"
                      >
                        {ep.title}
                      </Link>
                      <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-2">
                        {ep.published_at && <span>{ep.published_at.split('T')[0]}</span>}
                        {ep.duration_seconds > 0 && <span>{formatDuration(ep.duration_seconds)}</span>}
                        {ep.play_position > 0 && !ep.is_listened && (
                          <span className="text-blue-400">
                            {formatDuration(ep.play_position)} 处
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex-shrink-0 mt-1">
                      {ep.is_listened ? (
                        <CheckCircle size={16} className="text-green-400" />
                      ) : (
                        <Circle size={16} className="text-gray-200" />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
