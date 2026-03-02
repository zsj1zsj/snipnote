import { useState, useEffect } from 'react';
import { Clock, CheckCircle, BookOpen } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import api from '../api';

export default function Review() {
  const [due, setDue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [completed, setCompleted] = useState(0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);

  useEffect(() => {
    loadDue();
  }, []);

  const loadDue = async () => {
    setLoading(true);
    try {
      const data = await api.getNextReview(20);
      setDue(data);
    } catch (err) {
      console.error('Failed to load due reviews:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleReview = async (quality) => {
    if (!due[currentIndex]) return;
    try {
      await api.submitReview(due[currentIndex].id, quality);
      setShowAnswer(false);
      if (currentIndex >= due.length - 1) {
        setCurrentIndex(0);
      } else {
        setCurrentIndex((prev) => prev + 1);
      }
      setCompleted((prev) => prev + 1);
      // Remove the reviewed item from the list
      setDue((prev) => prev.filter((_, i) => i !== currentIndex));
    } catch (err) {
      console.error('Failed to submit review:', err);
    }
  };

  const qualityButtons = [
    { quality: 0, label: '0', desc: '完全忘记', color: 'bg-red-500 hover:bg-red-600' },
    { quality: 1, label: '1', desc: '错误', color: 'bg-red-400 hover:bg-red-500' },
    { quality: 2, label: '2', desc: '困难', color: 'bg-orange-400 hover:bg-orange-500' },
    { quality: 3, label: '3', desc: '一般', color: 'bg-blue-400 hover:bg-blue-500' },
    { quality: 4, label: '4', desc: '良好', color: 'bg-green-400 hover:bg-green-500' },
    { quality: 5, label: '5', desc: '完美', color: 'bg-green-500 hover:bg-green-600' },
  ];

  if (loading) {
    return (
      <div className="page-container">
        <div className="flex items-center justify-center py-20">
          <div className="spinner w-8 h-8"></div>
        </div>
      </div>
    );
  }

  const currentHighlight = due[currentIndex];

  return (
    <div className="page-container">
      <h1 className="page-title flex items-center gap-3">
        <Clock size={28} className="text-blue-500" />
        复习模式
      </h1>

      {/* Progress */}
      <div className="card p-4 mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-800">{due.length}</div>
              <div className="text-sm text-gray-400">剩余</div>
            </div>
            <div className="w-px h-10 bg-gray-200"></div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">{completed}</div>
              <div className="text-sm text-gray-400">已完成</div>
            </div>
          </div>
          <div className="flex items-center gap-2 text-green-600">
            <CheckCircle size={20} />
            <span className="font-medium">加油!</span>
          </div>
        </div>
      </div>

      {due.length === 0 ? (
        <div className="card p-12 text-center">
          <CheckCircle size={64} className="mx-auto text-green-400 mb-6" />
          <h2 className="text-xl font-semibold text-gray-700 mb-2">太棒了!</h2>
          <p className="text-gray-500">今天没有需要复习的内容了</p>
        </div>
      ) : currentHighlight ? (
        <div className="card p-6">
          {/* Meta */}
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-4 pb-4 border-b border-gray-100">
            {currentHighlight.source && (
              <>
                <BookOpen size={14} />
                <span>{currentHighlight.source}</span>
                {currentHighlight.author && <span>- {currentHighlight.author}</span>}
              </>
            )}
          </div>

          {/* Content */}
          <div className="prose-custom mb-8">
            <ReactMarkdown>{currentHighlight.text}</ReactMarkdown>
          </div>

          {/* Show answer button */}
          {!showAnswer && (
            <button
              onClick={() => setShowAnswer(true)}
              className="w-full py-4 bg-gray-900 text-white rounded-xl font-medium hover:bg-gray-800 transition-colors text-lg"
            >
              显示答案
            </button>
          )}

          {/* Rating buttons */}
          {showAnswer && (
            <div>
              <p className="text-center text-gray-500 mb-4">这次记忆的效果如何?</p>
              <div className="grid grid-cols-6 gap-2">
                {qualityButtons.map((btn) => (
                  <button
                    key={btn.quality}
                    onClick={() => handleReview(btn.quality)}
                    className={`${btn.color} text-white py-4 rounded-xl font-bold transition-all hover:scale-105`}
                  >
                    <div className="text-xl">{btn.label}</div>
                    <div className="text-xs opacity-80">{btn.desc}</div>
                  </button>
                ))}
              </div>
              <p className="text-center text-xs text-gray-400 mt-3">
                0=完全忘记 1=错误 2=困难 3=一般 4=良好 5=完美
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <CheckCircle size={64} className="mx-auto text-green-400 mb-6" />
          <h2 className="text-xl font-semibold text-gray-700 mb-2">完成!</h2>
          <p className="text-gray-500">所有复习内容已完成</p>
        </div>
      )}
    </div>
  );
}
