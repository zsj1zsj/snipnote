import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Headphones, Plus, Trash2, RefreshCw, Loader, ExternalLink } from 'lucide-react';
import api from '../api';
import { getCache, setCache, clearCache } from '../hooks/useCache';

const CACHE_KEY = 'podcast_shows';

export default function PodcastShows() {
  const [shows, setShows] = useState(() => getCache(CACHE_KEY) || []);
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const loadShows = async () => {
    try {
      const data = await api.getPodcastShows();
      setShows(data);
      setCache(CACHE_KEY, data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    if (!getCache(CACHE_KEY)) loadShows();
  }, []);

  const handleSubscribe = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await api.addPodcastShow(url.trim());
      if (result.already_subscribed) {
        setError('已经订阅过该节目');
      } else {
        setSuccess(`已订阅「${result.title}」，获取了 ${result.new_episodes} 集`);
        setUrl('');
        clearCache(CACHE_KEY);
        loadShows();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (showId) => {
    if (!confirm('确定要退订该节目吗？所有单集记录也会被删除。')) return;
    try {
      await api.deletePodcastShow(showId);
      clearCache(CACHE_KEY);
      loadShows();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleRefreshAll = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const result = await api.refreshPodcast();
      const total = result.total_new || 0;
      setSuccess(`刷新完成，共获取 ${total} 集新内容`);
      clearCache('podcast_episodes');
      clearCache(CACHE_KEY);
      loadShows();
    } catch (err) {
      setError(err.message);
    } finally {
      setRefreshing(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSubscribe();
  };

  return (
    <div className="page-container max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="page-title mb-0">Podcast 订阅</h1>
        <div className="flex gap-2">
          <Link to="/podcast/episodes" className="btn btn-secondary flex items-center gap-2">
            单集列表
          </Link>
          <button
            onClick={handleRefreshAll}
            disabled={refreshing || shows.length === 0}
            className="btn btn-secondary flex items-center gap-2"
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            刷新全部
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 text-green-600 px-4 py-3 rounded-lg mb-4">
          {success}
        </div>
      )}

      <div className="flex gap-3 mb-8">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入 Podcast RSS 地址..."
          className="input flex-1"
          autoFocus
        />
        <button
          onClick={handleSubscribe}
          disabled={loading || !url.trim()}
          className="btn btn-primary flex items-center gap-2 px-6"
        >
          {loading ? <Loader size={18} className="animate-spin" /> : <Plus size={18} />}
          订阅
        </button>
      </div>

      {shows.length === 0 ? (
        <div className="card p-8 text-center text-gray-400 text-sm">
          <Headphones size={40} className="mx-auto mb-3 text-gray-300" />
          还没有订阅任何 Podcast，输入 RSS 地址开始订阅
        </div>
      ) : (
        <div className="space-y-3">
          {shows.map((show) => (
            <div key={show.id} className="card p-4 flex items-center gap-4">
              {show.image_url ? (
                <img
                  src={show.image_url}
                  alt={show.title}
                  className="w-14 h-14 rounded-lg object-cover flex-shrink-0"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              ) : (
                <div className="w-14 h-14 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                  <Headphones size={24} className="text-gray-400" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-medium text-gray-800 truncate">{show.title}</div>
                {show.author && (
                  <div className="text-sm text-gray-500 truncate">{show.author}</div>
                )}
                <div className="text-xs text-gray-400 mt-1">
                  {show.total} 集 · {show.unlistened} 集未听
                  {show.last_fetched_at && ` · 最后刷新 ${show.last_fetched_at.split('T')[0]}`}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  to={`/podcast/episodes?show_id=${show.id}`}
                  className="btn btn-secondary text-sm px-3 py-1.5"
                >
                  查看单集
                </Link>
                {show.site_url && (
                  <a
                    href={show.site_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-gray-400 hover:text-gray-600 p-1.5"
                    title="访问网站"
                  >
                    <ExternalLink size={16} />
                  </a>
                )}
                <button
                  onClick={() => handleDelete(show.id)}
                  className="text-gray-400 hover:text-red-500 p-1.5"
                  title="退订"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
