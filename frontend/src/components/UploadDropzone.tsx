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
          setFiles((prev) =>
            prev.map((f) =>
              f.id === fileId
                ? { ...f, status: 'completed', replayId: result.replay_id }
                : f
            )
          );
          if (onUploadComplete) {
            onUploadComplete(uploadId, result.replay_id);
          }
          return;
        }

        if (result.status === 'failed') {
          setFiles((prev) =>
            prev.map((f) =>
              f.id === fileId
                ? { ...f, status: 'failed', error: result.error_message || 'Processing failed' }
                : f
            )
          );
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
          border-2 border-dashed rounded-xl p-8 text-center cursor-pointer
          transition-colors duration-200
          focus-within:ring-2 focus-within:ring-orange-500
          ${
            isDragActive
              ? 'border-orange-500 bg-orange-500/10'
              : 'border-gray-600 hover:border-gray-500 bg-gray-800/50'
          }
        `}
      >
        <input {...getInputProps()} aria-label="Upload replay files" />
        <div className="flex flex-col items-center gap-4">
          <svg
            className={`w-12 h-12 ${isDragActive ? 'text-orange-500' : 'text-gray-500'}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
          <div>
            <p className="text-lg font-medium text-white">
              {isDragActive ? 'Drop replays here' : 'Drag & drop replay files'}
            </p>
            <p className="text-sm text-gray-400 mt-1">
              or click to select files
            </p>
          </div>
        </div>
      </div>

      {/* File List */}
      {files.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-400">
              {files.length} file{files.length !== 1 ? 's' : ''}
              {pendingCount > 0 && ` (${pendingCount} processing)`}
            </span>
            {files.every((f) => f.status === 'completed' || f.status === 'failed') && (
              <button
                onClick={() => setFiles([])}
                className="text-orange-500 hover:underline focus:outline-none focus:underline focus:text-orange-400"
              >
                Clear all
              </button>
            )}
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {files.map((file) => (
              <div
                key={file.id}
                className="flex items-center gap-3 bg-gray-800 rounded-lg p-3"
              >
                {/* Status Icon */}
                <div className="flex-shrink-0" aria-hidden="true">
                  {file.status === 'completed' && (
                    <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                  {file.status === 'failed' && (
                    <svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  )}
                  {(file.status === 'uploading' || file.status === 'processing') && (
                    <svg className="w-5 h-5 text-orange-500 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                  )}
                  {file.status === 'pending' && (
                    <svg className="w-5 h-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  )}
                </div>

                {/* File Info */}
                <div className="flex-grow min-w-0">
                  <p className="text-sm text-white truncate">{file.file.name}</p>
                  <p className="text-xs text-gray-400">
                    {file.status === 'uploading' && 'Uploading...'}
                    {file.status === 'processing' && 'Analyzing... typically 30 seconds'}
                    {file.status === 'completed' && 'Analysis ready!'}
                    {file.status === 'failed' && (file.error || 'Failed')}
                    {file.status === 'pending' && 'Waiting...'}
                  </p>
                </div>

                {/* Size - human readable */}
                <span className="text-xs text-gray-500 flex-shrink-0">
                  {formatFileSize(file.file.size)}
                </span>

                {/* Action Buttons */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {/* View Replay button for completed uploads */}
                  {file.status === 'completed' && file.replayId && (
                    <Link
                      href={`/dashboard/replays/${file.replayId}`}
                      className="text-xs px-2 py-1 bg-orange-500 text-white rounded hover:bg-orange-600 transition-colors"
                    >
                      View
                    </Link>
                  )}

                  {/* Retry button for failed uploads */}
                  {file.status === 'failed' && (
                    <button
                      onClick={() => retryUpload(file.id)}
                      className="text-xs px-2 py-1 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
                    >
                      Retry
                    </button>
                  )}

                  {/* Remove Button */}
                  {(file.status === 'completed' || file.status === 'failed') && (
                    <button
                      onClick={() => removeFile(file.id)}
                      className="text-gray-500 hover:text-gray-300 focus:outline-none focus:text-orange-400"
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
