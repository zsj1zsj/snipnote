import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Calendar, RefreshCw, FileText } from 'lucide-react';
import api from '../api';

export default function DailyReport() {
  const [reports, setReports] = useState([]);
  const [selectedReport, setSelectedReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    loadReports();
  }, []);

  const loadReports = async () => {
    setLoading(true);
    try {
      const data = await api.getReports();
      setReports(data);
      if (data.length > 0 && !selectedReport) {
        loadReportContent(data[0].date);
      }
    } catch (err) {
      console.error('Failed to load reports:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadReportContent = async (date) => {
    try {
      const report = await api.getReport(date);
      setSelectedReport(report);
    } catch (err) {
      console.error('Failed to load report:', err);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await api.generateReport();
      loadReports();
    } catch (err) {
      console.error('Failed to generate report:', err);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="page-container">
      <div className="flex items-center justify-between mb-6">
        <h1 className="page-title flex items-center gap-3 mb-0">
          <Calendar size={28} className="text-gray-600" />
          阅读日报
        </h1>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="btn btn-primary flex items-center gap-2"
        >
          <RefreshCw size={16} className={generating ? 'animate-spin' : ''} />
          生成今日日报
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {/* Report list */}
        <div className="md:col-span-1">
          <div className="card overflow-hidden">
            <div className="bg-gray-50 px-4 py-3 border-b border-gray-100">
              <h2 className="font-medium text-gray-700">历史日报</h2>
            </div>
            <div className="max-h-[500px] overflow-y-auto">
              {loading ? (
                <div className="p-4 text-center">
                  <div className="spinner w-6 h-6 mx-auto"></div>
                </div>
              ) : reports.length === 0 ? (
                <div className="p-4 text-center text-gray-400">暂无日报</div>
              ) : (
                reports.map((report) => (
                  <button
                    key={report.id}
                    onClick={() => loadReportContent(report.date)}
                    className={`w-full px-4 py-3 text-left border-b border-gray-50 hover:bg-gray-50 transition-colors ${
                      selectedReport?.date === report.date ? 'bg-gray-100' : ''
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Calendar size={14} className="text-gray-400" />
                      <span className="font-medium text-gray-700">{report.date}</span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Report content */}
        <div className="md:col-span-3">
          {selectedReport ? (
            <div className="card p-6">
              <div className="report-content">
                <ReactMarkdown>{selectedReport.content}</ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="card p-12 text-center">
              <FileText size={48} className="mx-auto text-gray-300 mb-4" />
              <div className="text-gray-500">选择一份日报查看</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
