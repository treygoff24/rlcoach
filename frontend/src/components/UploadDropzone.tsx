// frontend/src/components/UploadDropzone.tsx
/**
 * Drag-and-drop file upload component for replay files.
 *
 * Supports:
 * - Drag-drop or click to select
 * - Multiple file upload
 * - Progress tracking per file
 * - Duplicate detection (SHA256)
 * - Exponential backoff polling
 * - Success navigation to replay
 * - Retry for failed uploads
 */

'use client';

import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import Link from 'next/link';
import { parseApiError, formatError } from '@/lib/errors';
import { useToast } from '@/components/Toast';

interface UploadFile {
  id: string;
  file: File;
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'failed';
  progress: number;
  error?: string;
  uploadId?: string;
  replayId?: string;
}

interface UploadDropzoneProps {
  onUploadComplete?: (uploadId: string, replayId?: string) => void;
  className?: string;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// Exponential backoff intervals in ms: 2s, 5s, 10s, 30s
const POLL_INTERVALS = [2000, 5000, 10000, 30000];

export function UploadDropzone({ onUploadComplete, className }: UploadDropzoneProps) {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const { addToast } = useToast();

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    // Filter for .replay files
    const replayFiles = acceptedFiles.filter((file) =>
      file.name.toLowerCase().endsWith('.replay')
    );

    if (replayFiles.length === 0) {
      return;
    }

    // Add files to state
    const newFiles: UploadFile[] = replayFiles.map((file) => ({
      id: Math.random().toString(36).substring(7),
      file,
      status: 'pending',
      progress: 0,
    }));

    setFiles((prev) => [...prev, ...newFiles]);

    // Upload each file
    for (const uploadFile of newFiles) {
      await uploadSingleFile(uploadFile);
    }
  }, []);

  const uploadSingleFile = async (uploadFile: UploadFile) => {
    // Update status to uploading
    setFiles((prev) =>
      prev.map((f) =>
        f.id === uploadFile.id ? { ...f, status: 'uploading', progress: 0 } : f
      )
    );

    try {
      const formData = new FormData();
      formData.append('file', uploadFile.file);

      const response = await fetch('/api/v1/replays/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const { message } = parseApiError(response, body);
        throw new Error(message);
      }

      const result = await response.json();

      // Update status based on result
      setFiles((prev) =>
        prev.map((f) =>
          f.id === uploadFile.id
            ? {
                ...f,
                status: result.status === 'completed' ? 'completed' : 'processing',
                progress: 100,
                uploadId: result.upload_id,
                replayId: result.replay_id,
              }
            : f
        )
      );

      // Start polling for processing status if needed
      if (result.status === 'pending' || result.status === 'processing') {
        pollUploadStatus(uploadFile.id, result.upload_id);
      } else if (result.status === 'completed' && onUploadComplete) {
        onUploadComplete(result.upload_id, result.replay_id);
      }
    } catch (error) {
      const message = formatError(error);
      setFiles((prev) =>
        prev.map((f) =>
          f.id === uploadFile.id
            ? { ...f, status: 'failed', error: message }
            : f
        )
      );
      addToast({
        type: 'error',
        title: 'Upload failed',
        description: message,
      });
    }
  };

  const pollUploadStatus = async (fileId: string, uploadId: string) => {
    const maxDuration = 5 * 60 * 1000; // 5 minutes max
    const startTime = Date.now();
    let pollIndex = 0;

    const poll = async () => {
      const elapsed = Date.now() - startTime;
      if (elapsed >= maxDuration) {
        setFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? {
                  ...f,
                  status: 'failed',
                  error: 'Processing is taking longer than expected. Check status later.',
                }
              : f
          )
        );
        return;
      }

      try {
        const response = await fetch(`/api/v1/replays/uploads/${uploadId}`);
        if (!response.ok) {
          throw new Error('Failed to get status');
        }

        const result = await response.json();

        if (result.status === 'completed') {
          setFiles((prev) => {
            const file = prev.find((f) => f.id === fileId);
            if (file) {
              addToast({
                type: 'success',
                title: 'Analysis complete',
                description: `${file.file.name} is ready to view.`,
              });
            }
            return prev.map((f) =>
              f.id === fileId
                ? { ...f, status: 'completed', replayId: result.replay_id }
                : f
            );
          });
          if (onUploadComplete) {
            onUploadComplete(uploadId, result.replay_id);
          }
          return;
        }

        if (result.status === 'failed') {
          const errorMessage = result.error_message || 'Processing failed';
          setFiles((prev) => {
            const file = prev.find((f) => f.id === fileId);
            if (file) {
              addToast({
                type: 'error',
                title: 'Analysis failed',
                description: `${file.file.name}: ${errorMessage}`,
              });
            }
            return prev.map((f) =>
              f.id === fileId
                ? { ...f, status: 'failed', error: errorMessage }
                : f
            );
          });
          return;
        }

        // Continue polling with exponential backoff
        const interval = POLL_INTERVALS[Math.min(pollIndex, POLL_INTERVALS.length - 1)];
        pollIndex++;
        setTimeout(poll, interval);
      } catch (error) {
        // On network error, retry with backoff
        const interval = POLL_INTERVALS[Math.min(pollIndex, POLL_INTERVALS.length - 1)];
        pollIndex++;
        setTimeout(poll, interval);
      }
    };

    poll();
  };

  const retryUpload = async (fileId: string) => {
    const file = files.find((f) => f.id === fileId);
    if (!file) return;

    // Reset status
    setFiles((prev) =>
      prev.map((f) =>
        f.id === fileId ? { ...f, status: 'pending', error: undefined, progress: 0 } : f
      )
    );

    await uploadSingleFile(file);
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/octet-stream': ['.replay'],
    },
    multiple: true,
  });

  const removeFile = (fileId: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== fileId));
  };

  const pendingCount = files.filter(
    (f) => f.status === 'pending' || f.status === 'uploading' || f.status === 'processing'
  ).length;

  return (
    <div className={className}>
      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={`
          relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer
          transition-all duration-300 group overflow-hidden
          focus-within:ring-2 focus-within:ring-boost focus-within:ring-offset-2 focus-within:ring-offset-void
          ${
            isDragActive
              ? 'border-fire bg-fire/10 scale-[1.02]'
              : 'border-white/20 hover:border-white/40 bg-white/[0.02] hover:bg-white/[0.04]'
          }
        `}
      >
        <input {...getInputProps()} aria-label="Upload replay files" />

        {/* Animated background gradient */}
        <div className={`
          absolute inset-0 bg-gradient-to-br from-fire/10 via-transparent to-boost/10
          transition-opacity duration-300
          ${isDragActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-50'}
        `} />

        {/* Corner accents */}
        <div className="absolute top-0 left-0 w-12 h-12 border-t-2 border-l-2 border-fire/30 rounded-tl-2xl" />
        <div className="absolute bottom-0 right-0 w-12 h-12 border-b-2 border-r-2 border-boost/30 rounded-br-2xl" />

        <div className="relative flex flex-col items-center gap-5">
          {/* Upload icon with animation */}
          <div className={`
            relative w-16 h-16 rounded-2xl flex items-center justify-center
            transition-all duration-300
            ${isDragActive
              ? 'bg-fire/20 scale-110'
              : 'bg-white/5 group-hover:bg-white/10'
            }
          `}>
            <svg
              className={`w-8 h-8 transition-all duration-300 ${
                isDragActive
                  ? 'text-fire animate-bounce'
                  : 'text-white/50 group-hover:text-white/80'
              }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            {isDragActive && (
              <div className="absolute inset-0 rounded-2xl border-2 border-fire animate-pulse-ring" />
            )}
          </div>

          <div>
            <p className="text-lg font-semibold text-white">
              {isDragActive ? 'Release to upload' : 'Drag & drop replay files'}
            </p>
            <p className="text-sm text-white/50 mt-1">
              or click to browse your files
            </p>
          </div>

          {/* File type hint */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10">
            <div className="w-1.5 h-1.5 rounded-full bg-boost" />
            <span className="text-xs text-white/50">.replay files only</span>
          </div>
        </div>
      </div>

      {/* File List */}
      {files.length > 0 && (
        <div className="mt-6 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-white/50">
              {files.length} file{files.length !== 1 ? 's' : ''}
              {pendingCount > 0 && (
                <span className="ml-2 text-boost">
                  ({pendingCount} processing)
                </span>
              )}
            </span>
            {files.every((f) => f.status === 'completed' || f.status === 'failed') && (
              <button
                onClick={() => setFiles([])}
                className="text-sm text-white/50 hover:text-white transition-colors focus:outline-none focus:text-fire"
              >
                Clear all
              </button>
            )}
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {files.map((file, index) => (
              <div
                key={file.id}
                className="group/file flex items-center gap-4 p-4 rounded-xl bg-white/[0.03] border border-white/5 hover:border-white/10 transition-all duration-200 animate-slide-up opacity-0 [animation-fill-mode:forwards]"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {/* Status Icon */}
                <div className="flex-shrink-0" aria-hidden="true">
                  {file.status === 'completed' && (
                    <div className="w-8 h-8 rounded-lg bg-victory/20 flex items-center justify-center">
                      <svg className="w-4 h-4 text-victory" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                  )}
                  {file.status === 'failed' && (
                    <div className="w-8 h-8 rounded-lg bg-defeat/20 flex items-center justify-center">
                      <svg className="w-4 h-4 text-defeat" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </div>
                  )}
                  {(file.status === 'uploading' || file.status === 'processing') && (
                    <div className="w-8 h-8 rounded-lg bg-fire/20 flex items-center justify-center">
                      <svg className="w-4 h-4 text-fire animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                      </svg>
                    </div>
                  )}
                  {file.status === 'pending' && (
                    <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center">
                      <svg className="w-4 h-4 text-white/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                  )}
                </div>

                {/* File Info */}
                <div className="flex-grow min-w-0">
                  <p className="text-sm font-medium text-white truncate">{file.file.name}</p>
                  <p className="text-xs text-white/40 mt-0.5">
                    {file.status === 'uploading' && 'Uploading...'}
                    {file.status === 'processing' && 'Analyzing replay...'}
                    {file.status === 'completed' && 'Ready to view'}
                    {file.status === 'failed' && (file.error || 'Failed')}
                    {file.status === 'pending' && 'Queued'}
                  </p>
                </div>

                {/* Size */}
                <span className="text-xs text-white/50 flex-shrink-0">
                  {formatFileSize(file.file.size)}
                </span>

                {/* Action Buttons */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {file.status === 'completed' && file.replayId && (
                    <Link
                      href={`/replays/${file.replayId}`}
                      className="px-3 py-1.5 text-xs font-semibold bg-fire text-white rounded-lg hover:bg-fire-600 transition-colors shadow-glow-fire"
                    >
                      View
                    </Link>
                  )}

                  {file.status === 'failed' && (
                    <button
                      onClick={() => retryUpload(file.id)}
                      className="px-3 py-1.5 text-xs font-semibold bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
                    >
                      Retry
                    </button>
                  )}

                  {(file.status === 'completed' || file.status === 'failed') && (
                    <button
                      onClick={() => removeFile(file.id)}
                      className="p-1.5 text-white/50 hover:text-white transition-colors rounded-lg hover:bg-white/5 focus:outline-none focus:text-fire"
                      aria-label={`Remove ${file.file.name}`}
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default UploadDropzone;
