import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Headphones, Plus, Trash2, RefreshCw, Loader, ExternalLink, Upload, Download, Search } from 'lucide-react';
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
  const fileInputRef = useRef(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [subscribing, setSubscribing] = useState({});

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

  const handleExportOpml = () => {
    window.open(api.exportPodcastOpml(), '_blank');
  };

  const handleImportOpml = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setError(null);
    try {
      const result = await api.importPodcastOpml(text);
      setSuccess(`开始导入 ${result.count} 个订阅源，后台处理中…`);
      setTimeout(() => { clearCache(CACHE_KEY); loadShows(); }, 3000);
    } catch (err) {
      setError(err.message);
    }
    e.target.value = '';
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchResults([]);
    setError(null);
    try {
      const results = await api.searchPodcasts(searchQuery.trim());
      setSearchResults(results);
      if (results.length === 0) setError('未找到相关节目');
    } catch (err) {
      setError(err.message);
    } finally {
      setSearching(false);
    }
  };

  const handleSubscribeFromSearch = async (feedUrl, title) => {
    setSubscribing(prev => ({ ...prev, [feedUrl]: true }));
    setError(null);
    try {
      const result = await api.addPodcastShow(feedUrl);
      if (result.already_subscribed) {
        setSuccess(`「${title}」已在订阅列表中`);
      } else {
        setSuccess(`已订阅「${result.title}」，获取了 ${result.new_episodes} 集`);
        clearCache(CACHE_KEY);
        loadShows();
      }
      setSearchResults([]);
      setSearchQuery('');
    } catch (err) {
      setError(err.message);
    } finally {
      setSubscribing(prev => ({ ...prev, [feedUrl]: false }));
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSubscribe();
  };

  return (
    <div className="page-container max-w-3xl">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-6">
        <h1 className="page-title mb-0">Podcast 订阅</h1>
        <div className="flex flex-wrap gap-2">
          <Link to="/podcast/episodes" className="btn btn-secondary flex items-center gap-2">
            <span className="hidden sm:inline">单集列表</span>
            <span className="sm:hidden text-sm">单集</span>
          </Link>
          <button
            onClick={handleRefreshAll}
            disabled={refreshing || shows.length === 0}
            className="btn btn-secondary flex items-center gap-2"
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">刷新全部</span>
          </button>
          <label className="btn btn-secondary flex items-center gap-2 cursor-pointer">
            <Upload size={16} />
            <span className="hidden sm:inline">导入 OPML</span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".opml,.xml"
              className="hidden"
              onChange={handleImportOpml}
            />
          </label>
          {shows.length > 0 && (
            <button
              onClick={handleExportOpml}
              className="btn btn-secondary flex items-center gap-2"
            >
              <Download size={16} />
              <span className="hidden sm:inline">导出 OPML</span>
            </button>
          )}
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

      {/* Search box */}
      <div className="flex gap-3 mb-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="搜索节目名称..."
            className="input pl-9 w-full"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={searching || !searchQuery.trim()}
          className="btn btn-secondary flex items-center gap-2"
        >
          {searching ? <Loader size={16} className="animate-spin" /> : <Search size={16} />}
          搜索
        </button>
      </div>

      {/* Search results */}
      {searchResults.length > 0 && (
        <div className="card divide-y divide-gray-100 mb-6">
          {searchResults.map((item) => (
            <div key={item.feed_url} className="p-3 flex items-center gap-3">
              {item.image_url ? (
                <img src={item.image_url} alt={item.title} className="w-12 h-12 rounded-lg object-cover flex-shrink-0" onError={(e) => { e.target.style.display = 'none'; }} />
              ) : (
                <div className="w-12 h-12 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                  <Headphones size={20} className="text-gray-400" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-medium text-gray-800 text-sm truncate">{item.title}</div>
                <div className="text-xs text-gray-400 truncate">{item.author}{item.genre && ` · ${item.genre}`}</div>
              </div>
              <button
                onClick={() => handleSubscribeFromSearch(item.feed_url, item.title)}
                disabled={!!subscribing[item.feed_url]}
                className="btn btn-primary text-xs px-3 py-1.5 flex-shrink-0"
              >
                {subscribing[item.feed_url] ? <Loader size={14} className="animate-spin" /> : '订阅'}
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row mb-8">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="或直接输入 RSS 地址..."
          className="input flex-1"
        />
        <button
          onClick={handleSubscribe}
          disabled={loading || !url.trim()}
          className="btn btn-primary flex items-center justify-center gap-2 w-full sm:w-auto sm:px-6"
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
            <div key={show.id} className="card p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
              <div className="flex items-center gap-3 sm:gap-4 flex-1 min-w-0">
                {show.image_url ? (
                  <img
                    src={show.image_url}
                    alt={show.title}
                    className="w-12 h-12 sm:w-14 sm:h-14 rounded-lg object-cover flex-shrink-0"
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                ) : (
                  <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                    <Headphones size={24} className="text-gray-400" />
                  </div>
                )}
                <Link to={`/podcast/show/${show.id}`} className="flex-1 min-w-0 hover:opacity-75">
                  <div className="font-medium text-gray-800 truncate">{show.title}</div>
                  {show.author && (
                    <div className="text-sm text-gray-500 truncate">{show.author}</div>
                  )}
                  <div className="text-xs text-gray-400 mt-1">
                    {show.total} 集 · {show.unlistened} 集未听
                    {show.last_fetched_at && ` · 最后刷新 ${show.last_fetched_at.split('T')[0]}`}
                  </div>
                </Link>
              </div>
              <div className="flex items-center gap-2 self-end sm:self-auto">
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
                    className="text-gray-400 hover:text-gray-600 p-2.5"
                    title="访问网站"
                  >
                    <ExternalLink size={16} />
                  </a>
                )}
                <button
                  onClick={() => handleDelete(show.id)}
                  className="text-gray-400 hover:text-red-500 p-2.5"
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
