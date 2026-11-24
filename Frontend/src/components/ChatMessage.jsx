import Icon from "./Icon";

function safeSourceUrl(value) {
  if (typeof value !== "string") return null;

  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.href
      : null;
  } catch {
    return null;
  }
}

export default function ChatMessage({
  message,
  onSpeak,
  onRetry,
  isSpeaking,
  isLoading,
}) {
  const isAssistant = message.role === "assistant";
  const sources = Array.isArray(message.sources) ? message.sources : [];

  return (
    <article
      className={`chat-message${isAssistant ? " chat-message-assistant" : " chat-message-user"}${message.isError ? " chat-message-error" : ""}`}
    >
      {isAssistant && (
        <span className="chat-avatar">
          <Icon name="spark" size={16} />
        </span>
      )}

      <div className="chat-message-content">
        <span className="chat-sender">
          {isAssistant ? "Schobot" : "You"}
        </span>

        <p dir="auto">{message.text}</p>

        {isAssistant && sources.length > 0 && (
          <div className="chat-sources">
            <strong>Scholarship sources</strong>
            <ul>
              {sources.map((source, index) => {
                const sourceUrl = safeSourceUrl(source.official_link);
                const sourceName = source.scholarship_name || "Scholarship record";
                return (
                  <li key={source.scholarship_id || `${sourceName}-${index}`}>
                    {sourceUrl ? (
                      <a
                        href={sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {sourceName}
                      </a>
                    ) : (
                      <span>{sourceName}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {isAssistant && (
          <div className="chat-message-actions">
            {!message.isError && onSpeak && (
              <button
                type="button"
                onClick={() => onSpeak(message)}
                aria-label={isSpeaking ? "Stop speaking" : "Read answer aloud"}
                title={isSpeaking ? "Stop speaking" : "Read answer aloud"}
              >
                <Icon name={isSpeaking ? "stop" : "speaker"} size={15} />
                <span>{isSpeaking ? "Stop" : "Listen"}</span>
              </button>
            )}
            {message.isError && message.retryQuestion && onRetry && (
              <button
                type="button"
                onClick={() => onRetry(message)}
                disabled={isLoading}
              >
                <Icon name="refresh" size={15} />
                <span>Retry</span>
              </button>
            )}
          </div>
        )}
      </div>

      {!isAssistant && (
        <span className="chat-avatar chat-avatar-user">SP</span>
      )}
    </article>
  );
}
