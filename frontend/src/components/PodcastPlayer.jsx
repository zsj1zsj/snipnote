import { useState, useEffect, useRef } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Headphones, Loader, Sparkles, Play, Pause, SkipBack, SkipForward, BookmarkPlus } from 'lucide-react';
import api from '../api';
import { usePlayer } from '../contexts/PlayerContext';
import { getCache, setCache } from '../hooks/useCache';

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
  } catch { return ''; }
}

export default function PodcastPlayer() {
  const { id } = useParams();
  const cacheKey = `podcast_episode_${id}`;
  const { loadEpisode, togglePlay, seek, skip, setRate, isPlaying, currentTime, duration, rate } = usePlayer();

  const cached = getCache(cacheKey);
  const [episode, setEpisode] = useState(cached?.episode || null);
  const [loading, setLoading] = useState(!cached);
  const [isListened, setIsListened] = useState(cached?.episode?.is_listened || 0);
  const [aiSummary, setAiSummary] = useState(cached?.episode?.ai_summary || '');
  const [summarizing, setSummarizing] = useState(false);
  const [savedHighlightId, setSavedHighlightId] = useState(null);
  const [saving, setSaving] = useState(false);
  const seekingRef = useRef(false);

  // Load episode data
  useEffect(() => {
    if (cached) {
      setEpisode(cached.episode);
      setIsListened(cached.episode.is_listened);
      setAiSummary(cached.episode.ai_summary || '');
      loadEpisode(cached.episode, cached.episode.play_position || 0);
      return;
    }
    api.getPodcastEpisode(id)
      .then((data) => {
        setEpisode(data);
        setIsListened(data.is_listened);
        setAiSummary(data.ai_summary || '');
        setCache(cacheKey, { episode: data });
        loadEpisode(data, data.play_position || 0);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  // Sync is_listened from context (audio ended → context marked listened)
  useEffect(() => {
    if (episode) setIsListened(episode.is_listened || 0);
  }, [episode?.is_listened]);

  const handleSeekChange = (e) => {
    seekingRef.current = true;
    seek((parseFloat(e.target.value) / 100) * duration);
    setTimeout(() => { seekingRef.current = false; }, 200);
  };

  const handleToggleListened = async () => {
    try {
      const result = await api.toggleEpisodeListened(parseInt(id));
      setIsListened(result.is_listened);
      const c = getCache(cacheKey);
      if (c?.episode) { c.episode.is_listened = result.is_listened; setCache(cacheKey, c); }
      const listCache = getCache('podcast_episodes');
      if (listCache?.episodes) {
        listCache.episodes = listCache.episodes.map(ep =>
          ep.id === parseInt(id) ? { ...ep, is_listened: result.is_listened } : ep
        );
        setCache('podcast_episodes', listCache);
      }
    } catch (err) { console.error(err); }
  };

  const handleSaveHighlight = async () => {
    setSaving(true);
    try {
      const result = await api.savePodcastHighlight(parseInt(id));
      setSavedHighlightId(result.highlight_id);
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleSummarize = async () => {
    setSummarizing(true);
    try {
      const result = await api.summarizePodcastEpisode(parseInt(id));
      if (result.cached) {
        setAiSummary(result.summary);
        const c = getCache(cacheKey);
        if (c?.episode) { c.episode.ai_summary = result.summary; setCache(cacheKey, c); }
        setSummarizing(false);
        return;
      }
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const ep = await api.getPodcastEpisode(parseInt(id));
          if (ep.ai_summary) {
            setAiSummary(ep.ai_summary);
            const c = getCache(cacheKey);
            if (c?.episode) { c.episode.ai_summary = ep.ai_summary; setCache(cacheKey, c); }
            clearInterval(poll);
            setSummarizing(false);
          } else if (attempts >= 36) { clearInterval(poll); setSummarizing(false); }
        } catch { clearInterval(poll); setSummarizing(false); }
      }, 5000);
    } catch (err) { console.error(err); setSummarizing(false); }
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  if (loading) {
    return (
      <div className="page-container max-w-3xl">
        <div className="text-center py-12 text-gray-400">
          <Loader size={24} className="animate-spin mx-auto mb-2" />
          加载中...
        </div>
      </div>
    );
  }

  if (!episode) {
    return (
      <div className="page-container max-w-3xl">
        <div className="card p-8 text-center text-gray-400">单集不存在</div>
      </div>
    );
  }

  const coverImage = episode.image_url || episode.show_image_url;

  return (
    <div className="page-container max-w-3xl pb-20">
      <div className="flex items-center justify-between mb-6">
        <Link
          to="/podcast/episodes"
          className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-700 transition-colors"
        >
          <ArrowLeft size={18} />
          返回单集列表
        </Link>
        <button
          onClick={handleToggleListened}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
            isListened
              ? 'bg-green-100 text-green-700 hover:bg-green-200'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          <Headphones size={16} />
          {isListened ? '已听' : '标记已听'}
        </button>
      </div>

      {/* Episode header */}
      <div className="card p-6 mb-4">
        <div className="flex gap-5">
          {coverImage ? (
            <img
              src={coverImage}
              alt={episode.title}
              className="w-24 h-24 rounded-xl object-cover flex-shrink-0"
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          ) : (
            <div className="w-24 h-24 rounded-xl bg-gray-100 flex items-center justify-center flex-shrink-0">
              <Headphones size={36} className="text-gray-400" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-gray-900 leading-snug mb-2">{episode.title}</h1>
            <div className="text-sm text-gray-500 space-y-0.5">
              {episode.show_title && <div className="font-medium text-gray-700">{episode.show_title}</div>}
              {episode.author && <div>{episode.author}</div>}
              <div className="flex items-center gap-2 text-gray-400">
                {episode.published_at && <span>{formatDate(episode.published_at)}</span>}
                {episode.duration_seconds > 0 && (
                  <><span>·</span><span>{formatTime(episode.duration_seconds)}</span></>
                )}
                {episode.season_number && episode.episode_number && (
                  <><span>·</span><span>S{episode.season_number}E{episode.episode_number}</span></>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Custom audio player */}
      <div className="card p-5 mb-4">
        {/* Progress bar */}
        <div className="mb-4">
          <input
            type="range"
            min="0"
            max="100"
            step="0.1"
            value={progress}
            onChange={handleSeekChange}
            className="w-full h-1.5 appearance-none bg-gray-200 rounded-full cursor-pointer accent-gray-900"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>{formatTime(currentTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
        </div>

        {/* Controls row */}
        <div className="flex items-center justify-between">
          {/* Skip back */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => skip(-15)}
              className="flex flex-col items-center text-gray-500 hover:text-gray-800 transition-colors"
              title="后退 15 秒"
            >
              <SkipBack size={22} />
              <span className="text-xs mt-0.5">15</span>
            </button>

            {/* Play/Pause */}
            <button
              onClick={togglePlay}
              className="w-12 h-12 flex items-center justify-center rounded-full bg-gray-900 text-white hover:bg-gray-700 transition-colors shadow-md"
            >
              {isPlaying ? <Pause size={20} /> : <Play size={20} className="ml-0.5" />}
            </button>

            {/* Skip forward */}
            <button
              onClick={() => skip(30)}
              className="flex flex-col items-center text-gray-500 hover:text-gray-800 transition-colors"
              title="前进 30 秒"
            >
              <SkipForward size={22} />
              <span className="text-xs mt-0.5">30</span>
            </button>
          </div>

          {/* Speed selector */}
          <div className="flex items-center gap-1">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => setRate(s)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                  rate === s
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-500 hover:bg-gray-100'
                }`}
              >
                {s === 1 ? '1x' : `${s}x`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* AI Summary */}
      <div className="card p-5 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <Sparkles size={14} className="text-purple-500" />
            AI 总结
          </h2>
          {!aiSummary && (
            <button
              onClick={handleSummarize}
              disabled={summarizing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-50 text-purple-700 hover:bg-purple-100 transition-all disabled:opacity-50"
            >
              {summarizing
                ? <><Loader size={12} className="animate-spin" />生成中…</>
                : <><Sparkles size={12} />生成总结</>}
            </button>
          )}
        </div>
        {aiSummary ? (
          <>
            <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line mb-3">{aiSummary}</div>
            {savedHighlightId ? (
              <Link
                to={`/highlight/${savedHighlightId}`}
                className="inline-flex items-center gap-1.5 text-xs text-green-600 hover:text-green-700 font-medium"
              >
                <BookmarkPlus size={13} />
                已保存到摘录，点击查看
              </Link>
            ) : (
              <button
                onClick={handleSaveHighlight}
                disabled={saving}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-50 text-gray-600 hover:bg-gray-100 transition-all disabled:opacity-50"
              >
                {saving ? <Loader size={12} className="animate-spin" /> : <BookmarkPlus size={12} />}
                保存为摘录
              </button>
            )}
          </>
        ) : (
          <div className="text-sm text-gray-400">
            {summarizing ? '正在分析音频内容，这可能需要 1-2 分钟…' : '点击「生成总结」，AI 将分析本集内容并生成摘要'}
          </div>
        )}
      </div>

      {/* Description */}
      {episode.description && (
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">节目简介</h2>
          <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">{episode.description}</div>
        </div>
      )}
    </div>
  );
}
