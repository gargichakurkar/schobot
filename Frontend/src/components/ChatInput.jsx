import Icon from "./Icon";

export default function ChatInput({
  value,
  onChange,
  onSubmit,
  isLoading,
  isListening,
  onVoiceToggle,
}) {
  return (
    <form className="chat-input-form" onSubmit={onSubmit}>
      <label className="sr-only" htmlFor="assistant-prompt">Ask Schobot anything...</label>
      <input
        autoComplete="off"
        id="assistant-prompt"
        maxLength={1990}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Ask Schobot anything..."
        type="text"
        value={value}
      />
      <button
        aria-label={isListening ? "Stop voice input" : "Start voice input"}
        className={`voice-input-button${isListening ? " is-listening" : ""}`}
        disabled={isLoading}
        onClick={onVoiceToggle}
        type="button"
      >
        <Icon name={isListening ? "stop" : "microphone"} size={17} />
      </button>
      <button
        aria-label="Send message"
        className="send-button"
        disabled={!value.trim() || isLoading}
        type="submit"
      >
        <Icon name="send" size={17} />
      </button>
    </form>
  );
}
