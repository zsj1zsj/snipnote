import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Rss, Plus, Trash2, RefreshCw, Loader, ExternalLink } from 'lucide-react';
import api from '../api';
import { getCache, setCache, clearCache } from '../hooks/useCache';

const CACHE_KEY = 'rss_feeds';

export default function RssFeeds() {
  const [feeds, setFeeds] = useState(() => getCache(CACHE_KEY) || []);
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const loadFeeds = async () => {
    try {
      const data = await api.getRssFeeds();
      setFeeds(data);
      setCache(CACHE_KEY, data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    if (!getCache(CACHE_KEY)) loadFeeds();
  }, []);

  const handleSubscribe = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await api.addRssFeed(url.trim());
      if (result.already_subscribed) {
        setError('已经订阅过该源');
      } else {
        setSuccess(`已订阅「${result.title}」，获取了 ${result.new_articles} 篇文章`);
        setUrl('');
        loadFeeds();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (feedId) => {
    if (!confirm('确定要退订该 RSS 源吗？所有文章也会被删除。')) return;
    try {
      await api.deleteRssFeed(feedId);
      loadFeeds();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleRefreshAll = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const result = await api.refreshRss();
      const total = Object.values(result.results).reduce((a, b) => a + b, 0);
      setSuccess(`刷新完成，共获取 ${total} 篇新文章`);
      clearCache('rss_articles');
      loadFeeds();
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
        <h1 className="page-title mb-0">RSS 订阅</h1>
        <div className="flex gap-2">
          <Link to="/rss/articles" className="btn btn-secondary flex items-center gap-2">
            文章列表
          </Link>
          <button
            onClick={handleRefreshAll}
            disabled={refreshing || feeds.length === 0}
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
          placeholder="输入 RSS 源地址..."
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

      {feeds.length === 0 ? (
        <div className="card p-8 text-center text-gray-400 text-sm">
          <Rss size={40} className="mx-auto mb-3 text-gray-300" />
          还没有订阅任何 RSS 源，输入地址开始订阅
        </div>
      ) : (
        <div className="space-y-3">
          {feeds.map((feed) => (
            <div key={feed.id} className="card p-4 flex items-center gap-4">
              <Rss size={20} className="text-orange-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-gray-800 truncate">{feed.title}</div>
                <div className="text-sm text-gray-400 truncate">{feed.url}</div>
                <div className="text-xs text-gray-400 mt-1">
                  {feed.total_articles} 篇文章 · {feed.unread_articles} 篇未读
                  {feed.last_fetched_at && ` · 最后刷新 ${feed.last_fetched_at.split('T')[0]}`}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  to={`/rss/articles?feed_id=${feed.id}`}
                  className="btn btn-secondary text-sm px-3 py-1.5"
                >
                  查看文章
                </Link>
                {feed.site_url && (
                  <a
                    href={feed.site_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-gray-400 hover:text-gray-600 p-1.5"
                    title="访问网站"
                  >
                    <ExternalLink size={16} />
                  </a>
                )}
                <button
                  onClick={() => handleDelete(feed.id)}
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
