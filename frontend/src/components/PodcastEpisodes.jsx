import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Headphones, Loader, Play } from 'lucide-react';
import api from '../api';
import { getCache, setCache } from '../hooks/useCache';

const CACHE_KEY = 'podcast_episodes';

function formatDuration(seconds) {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  } catch { return ''; }
}

export default function PodcastEpisodes() {
  const [searchParams] = useSearchParams();
  const initialShowId = searchParams.get('show_id') || '';

  const cached = getCache(CACHE_KEY);
  const [episodes, setEpisodes] = useState(cached?.episodes || []);
  const [shows, setShows] = useState(cached?.shows || []);
  const [showId, setShowId] = useState(cached?.showId ?? initialShowId);
  const [listenFilter, setListenFilter] = useState(cached?.listenFilter || 'all');
  const [loading, setLoading] = useState(!cached);

  const loadEpisodes = async (sid, lf) => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (sid) params.show_id = sid;
      if (lf !== 'all') params.is_listened = lf;
      const data = await api.getPodcastEpisodes(params);
      setEpisodes(data);
      setCache(CACHE_KEY, { episodes: data, shows, showId: sid, listenFilter: lf });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.getPodcastShows().then((data) => {
      setShows(data);
      if (cached) setCache(CACHE_KEY, { ...cached, shows: data });
    }).catch(console.error);
  }, []);

  useEffect(() => {
    if (cached && showId === (cached.showId ?? initialShowId) && listenFilter === (cached.listenFilter || 'all') && episodes.length > 0) {
      return;
    }
    loadEpisodes(showId, listenFilter);
  }, [showId, listenFilter]);

  const updateEpisodes = (updater) => {
    setEpisodes(prev => {
      const next = updater(prev);
      setCache(CACHE_KEY, { episodes: next, shows, showId, listenFilter });
      return next;
    });
  };

  const handleToggleListened = async (episodeId) => {
    try {
      const result = await api.toggleEpisodeListened(episodeId);
      updateEpisodes(prev => prev.map(ep => ep.id === episodeId ? { ...ep, is_listened: result.is_listened } : ep));
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="page-container max-w-3xl">
      <Link
        to="/podcast"
        className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-700 mb-6 transition-colors"
      >
        <ArrowLeft size={18} />
        返回订阅
      </Link>

      <h1 className="page-title">单集列表</h1>

      <div className="flex gap-3 mb-6">
        <select
          value={showId}
          onChange={(e) => setShowId(e.target.value)}
          className="input"
        >
          <option value="">所有节目</option>
          {shows.map((s) => (
            <option key={s.id} value={s.id}>{s.title}</option>
          ))}
        </select>
        <div className="flex gap-1">
          {[
            { value: 'all', label: '全部' },
            { value: 'unlistened', label: '未听' },
            { value: 'listened', label: '已听' },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => setListenFilter(opt.value)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                listenFilter === opt.value
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-500 hover:bg-gray-100'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">
          <Loader size={24} className="animate-spin mx-auto mb-2" />
          加载中...
        </div>
      ) : episodes.length === 0 ? (
        <div className="card p-8 text-center text-gray-400 text-sm">
          <Headphones size={40} className="mx-auto mb-3 text-gray-300" />
          暂无单集
        </div>
      ) : (
        <div className="space-y-2">
          {episodes.map((ep) => (
            <div
              key={ep.id}
              className={`card p-4 flex items-start gap-3 ${ep.is_listened ? 'opacity-60' : ''}`}
            >
              <div className="flex-1 min-w-0">
                <Link
                  to={`/podcast/episode/${ep.id}`}
                  className="font-medium text-gray-800 hover:text-blue-600 transition-colors block truncate"
                >
                  {ep.title}
                </Link>
                <div className="text-sm text-gray-400 mt-1 truncate">
                  {ep.show_title}
                  {ep.season_number && ep.episode_number && ` · S${ep.season_number}E${ep.episode_number}`}
                  {ep.duration_seconds > 0 && ` · ${formatDuration(ep.duration_seconds)}`}
                  {ep.published_at && ` · ${formatDate(ep.published_at)}`}
                </div>
                {ep.description && (
                  <div className="text-sm text-gray-500 mt-1 line-clamp-2">{ep.description}</div>
                )}
                {ep.play_position > 0 && !ep.is_listened && (
                  <div className="text-xs text-blue-500 mt-1">
                    上次播放到 {formatDuration(ep.play_position)}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <Link
                  to={`/podcast/episode/${ep.id}`}
                  className="text-gray-400 hover:text-blue-500 p-1.5"
                  title="播放"
                >
                  <Play size={16} />
                </Link>
                <button
                  onClick={() => handleToggleListened(ep.id)}
                  className={`p-1.5 ${ep.is_listened ? 'text-green-500' : 'text-gray-400 hover:text-green-500'}`}
                  title={ep.is_listened ? '标记未听' : '标记已听'}
                >
                  <Headphones size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
