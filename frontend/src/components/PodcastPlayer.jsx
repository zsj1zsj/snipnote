import { useState, useEffect, useRef } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Headphones, Loader, Sparkles } from 'lucide-react';
import api from '../api';
import { getCache, setCache } from '../hooks/useCache';

function formatDuration(seconds) {
  if (!seconds) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
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

  const cached = getCache(cacheKey);
  const [episode, setEpisode] = useState(cached?.episode || null);
  const [loading, setLoading] = useState(!cached);
  const [isListened, setIsListened] = useState(cached?.episode?.is_listened || 0);
  const [aiSummary, setAiSummary] = useState(cached?.episode?.ai_summary || '');
  const [summarizing, setSummarizing] = useState(false);

  const audioRef = useRef(null);
  const progressTimerRef = useRef(null);
  const initialPositionRef = useRef(0);

  useEffect(() => {
    if (cached) {
      setEpisode(cached.episode);
      setIsListened(cached.episode.is_listened);
      initialPositionRef.current = cached.episode.play_position || 0;
      return;
    }
    api.getPodcastEpisode(id)
      .then((data) => {
        setEpisode(data);
        setIsListened(data.is_listened);
        setAiSummary(data.ai_summary || '');
        initialPositionRef.current = data.play_position || 0;
        setCache(cacheKey, { episode: data });
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  // Restore play position once audio is ready
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !episode) return;

    const onCanPlay = () => {
      if (initialPositionRef.current > 0) {
        audio.currentTime = initialPositionRef.current;
      }
    };

    audio.addEventListener('canplay', onCanPlay, { once: true });
    return () => audio.removeEventListener('canplay', onCanPlay);
  }, [episode]);

  // Save play position every 10 seconds
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !episode) return;

    const onTimeUpdate = () => {
      if (progressTimerRef.current) return;
      progressTimerRef.current = setTimeout(() => {
        progressTimerRef.current = null;
        const pos = Math.floor(audio.currentTime);
        if (pos > 0) {
          api.updatePlayProgress(parseInt(id), pos).catch(() => {});
          // Update cache
          const c = getCache(cacheKey);
          if (c?.episode) {
            c.episode.play_position = pos;
            setCache(cacheKey, c);
          }
        }
      }, 10000);
    };

    const onEnded = () => {
      api.toggleEpisodeListened(parseInt(id)).then(() => {
        setIsListened(1);
        const c = getCache(cacheKey);
        if (c?.episode) {
          c.episode.is_listened = 1;
          setCache(cacheKey, c);
        }
        // Sync to episodes list cache
        const listCache = getCache('podcast_episodes');
        if (listCache?.episodes) {
          listCache.episodes = listCache.episodes.map(ep =>
            ep.id === parseInt(id) ? { ...ep, is_listened: 1 } : ep
          );
          setCache('podcast_episodes', listCache);
        }
      }).catch(() => {});
    };

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('ended', onEnded);
    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('ended', onEnded);
      if (progressTimerRef.current) {
        clearTimeout(progressTimerRef.current);
        progressTimerRef.current = null;
      }
    };
  }, [episode, id]);

  const handleSummarize = async () => {
    setSummarizing(true);
    try {
      const result = await api.summarizePodcastEpisode(parseInt(id));
      if (result.cached) {
        setAiSummary(result.summary);
        const c = getCache(cacheKey);
        if (c?.episode) { c.episode.ai_summary = result.summary; setCache(cacheKey, c); }
        return;
      }
      // Poll until summarization completes (up to 3 minutes)
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
          } else if (attempts >= 36) {
            clearInterval(poll);
            setSummarizing(false);
          }
        } catch { clearInterval(poll); setSummarizing(false); }
      }, 5000);
    } catch (err) {
      console.error(err);
      setSummarizing(false);
    }
  };

  const handleToggleListened = async () => {
    try {
      const result = await api.toggleEpisodeListened(parseInt(id));
      setIsListened(result.is_listened);
      const c = getCache(cacheKey);
      if (c?.episode) {
        c.episode.is_listened = result.is_listened;
        setCache(cacheKey, c);
      }
      const listCache = getCache('podcast_episodes');
      if (listCache?.episodes) {
        listCache.episodes = listCache.episodes.map(ep =>
          ep.id === parseInt(id) ? { ...ep, is_listened: result.is_listened } : ep
        );
        setCache('podcast_episodes', listCache);
      }
    } catch (err) {
      console.error(err);
    }
  };

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
    <div className="page-container max-w-3xl">
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
          title={isListened ? '标记未听' : '标记已听'}
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
                  <>
                    <span>·</span>
                    <span>{formatDuration(episode.duration_seconds)}</span>
                  </>
                )}
                {episode.season_number && episode.episode_number && (
                  <>
                    <span>·</span>
                    <span>S{episode.season_number}E{episode.episode_number}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Audio player */}
      <div className="card p-5 mb-4">
        <audio
          ref={audioRef}
          controls
          className="w-full"
          preload="metadata"
          src={episode.audio_url}
        >
          您的浏览器不支持 HTML5 音频播放。
        </audio>
        {episode.play_position > 0 && !isListened && (
          <div className="text-xs text-blue-500 mt-2 text-center">
            上次播放到 {formatDuration(episode.play_position)}，已自动恢复
          </div>
        )}
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
              {summarizing ? (
                <><Loader size={12} className="animate-spin" />生成中…</>
              ) : (
                <><Sparkles size={12} />生成总结</>
              )}
            </button>
          )}
        </div>
        {aiSummary ? (
          <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">
            {aiSummary}
          </div>
        ) : (
          <div className="text-sm text-gray-400">
            {summarizing
              ? '正在分析音频内容，这可能需要 1-2 分钟…'
              : '点击「生成总结」，AI 将分析本集内容并生成摘要'}
          </div>
        )}
      </div>

      {/* Description */}
      {episode.description && (
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">节目简介</h2>
          <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">
            {episode.description}
          </div>
        </div>
      )}
    </div>
  );
}
