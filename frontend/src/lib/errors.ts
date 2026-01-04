// frontend/src/lib/errors.ts
/**
 * Error utilities for mapping API errors to user-friendly messages.
 */

interface ErrorMapping {
  message: string;
  action?: string;
}

// HTTP status code to user-friendly message
const HTTP_ERROR_MESSAGES: Record<number, ErrorMapping> = {
  400: {
    message: 'Invalid request. Please check your input and try again.',
    action: 'Review your input',
  },
  401: {
    message: 'Your session has expired. Please sign in again.',
    action: 'Sign in',
  },
  402: {
    message: 'This feature requires a Pro subscription.',
    action: 'Upgrade to Pro',
  },
  403: {
    message: "You don't have permission to access this resource.",
    action: 'Contact support',
  },
  404: {
    message: "We couldn't find what you're looking for.",
    action: 'Go back',
  },
  409: {
    message: 'This action conflicts with existing data.',
    action: 'Refresh and try again',
  },
  413: {
    message: 'The file is too large. Maximum size is 10MB.',
    action: 'Choose a smaller file',
  },
  429: {
    message: "You're making requests too quickly. Please wait a moment.",
    action: 'Wait and retry',
  },
  500: {
    message: 'Something went wrong on our end. Please try again later.',
    action: 'Try again',
  },
  502: {
    message: 'Our servers are temporarily unavailable. Please try again.',
    action: 'Try again',
  },
  503: {
    message: 'Service is temporarily unavailable. Please try again later.',
    action: 'Try again later',
  },
  504: {
    message: 'Request timed out. Please try again.',
    action: 'Try again',
  },
};

// API error codes to user-friendly messages
const API_ERROR_MESSAGES: Record<string, ErrorMapping> = {
  // Auth errors
  INVALID_CREDENTIALS: {
    message: 'Invalid email or password.',
    action: 'Check your credentials',
  },
  SESSION_EXPIRED: {
    message: 'Your session has expired. Please sign in again.',
    action: 'Sign in',
  },
  OAUTH_CALLBACK_ERROR: {
    message: 'Sign-in was interrupted. Please try again.',
    action: 'Sign in again',
  },
  ACCOUNT_DISABLED: {
    message: 'Your account has been disabled.',
    action: 'Contact support',
  },

  // Subscription errors
  SUBSCRIPTION_REQUIRED: {
    message: 'This feature requires a Pro subscription.',
    action: 'Upgrade to Pro',
  },
  BUDGET_EXHAUSTED: {
    message: 'Your monthly AI budget has been used. It resets next billing cycle.',
    action: 'Wait for reset or upgrade',
  },
  PAYMENT_FAILED: {
    message: 'Payment failed. Please update your payment method.',
    action: 'Update payment',
  },

  // Upload errors
  FILE_TOO_LARGE: {
    message: 'File is too large. Maximum size is 10MB.',
    action: 'Choose a smaller file',
  },
  INVALID_FILE_TYPE: {
    message: 'Invalid file type. Please upload a .replay file.',
    action: 'Choose a replay file',
  },
  DUPLICATE_REPLAY: {
    message: 'This replay has already been uploaded.',
    action: 'Upload a different replay',
  },
  UPLOAD_FAILED: {
    message: 'Upload failed. Please try again.',
    action: 'Try again',
  },
  PROCESSING_TIMEOUT: {
    message: 'Processing is taking longer than expected.',
    action: 'Check status later',
  },

  // General errors
  VALIDATION_ERROR: {
    message: 'Please check your input and try again.',
    action: 'Review input',
  },
  RATE_LIMIT_EXCEEDED: {
    message: "You're making requests too quickly. Please slow down.",
    action: 'Wait and retry',
  },
  NETWORK_ERROR: {
    message: 'Unable to connect. Check your internet connection.',
    action: 'Check connection',
  },
};

/**
 * Get a user-friendly error message from an HTTP status code.
 */
export function getHttpErrorMessage(status: number): ErrorMapping {
  return (
    HTTP_ERROR_MESSAGES[status] || {
      message: 'An unexpected error occurred. Please try again.',
      action: 'Try again',
    }
  );
}

/**
 * Get a user-friendly error message from an API error code.
 */
export function getApiErrorMessage(code: string): ErrorMapping {
  return (
    API_ERROR_MESSAGES[code] || {
      message: 'An unexpected error occurred. Please try again.',
      action: 'Try again',
    }
  );
}

/**
 * Parse an API response error and return a user-friendly message.
 */
export function parseApiError(
  response: Response,
  body?: { detail?: string; code?: string; error?: string }
): ErrorMapping {
  // Check for known error codes first
  if (body?.code && API_ERROR_MESSAGES[body.code]) {
    return API_ERROR_MESSAGES[body.code];
  }

  // Fall back to HTTP status
  const httpError = getHttpErrorMessage(response.status);

  // If the API provided a detail message, use it
  if (body?.detail) {
    return {
      message: body.detail,
      action: httpError.action,
    };
  }

  return httpError;
}

/**
 * Format an error for display, handling various error types.
 */
export function formatError(error: unknown): string {
  if (error instanceof Error) {
    // Handle common network errors
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      return 'Unable to connect. Check your internet connection.';
    }
    if (error.name === 'AbortError') {
      return 'Request was cancelled.';
    }
    return error.message;
  }

  if (typeof error === 'string') {
    return error;
  }

  return 'An unexpected error occurred. Please try again.';
}

/**
 * Check if an error is a network connectivity error.
 */
export function isNetworkError(error: unknown): boolean {
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return true;
  }
  if (error instanceof Error && error.name === 'NetworkError') {
    return true;
  }
  return false;
}

/**
 * Check if an error is retriable.
 */
export function isRetriableError(status: number): boolean {
  return [408, 429, 500, 502, 503, 504].includes(status);
}
