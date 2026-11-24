import { useEffect, useRef, useState } from "react";
import ChatInput from "../components/ChatInput";
import ChatMessage from "../components/ChatMessage";
import Icon from "../components/Icon";
import { sendChatMessage } from "../apiClient";
import { getStudentId } from "../data/profile";

const HISTORY_KEY = "schobot-assistant-history";
const MAX_HISTORY_MESSAGES = 80;

const suggestions = [
  "Find scholarships for me",
  "Why am I eligible?",
  "What documents do I need?",
  "How do I apply?",
  "Show scholarships for my category",
];

function loadConversation() {
  if (typeof window === "undefined") return [];

  try {
    const stored = window.sessionStorage.getItem(HISTORY_KEY);
    if (!stored) return [];
    const parsed = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (message) =>
          message
          && ["user", "assistant"].includes(message.role)
          && typeof message.text === "string",
      )
      .slice(-MAX_HISTORY_MESSAGES)
      .map((message) => ({
        ...message,
        sources: Array.isArray(message.sources) ? message.sources : [],
      }));
  } catch (error) {
    console.warn("Could not restore the assistant conversation.", error);
    return [];
  }
}

export default function AIAssistant() {
  const [messages, setMessages] = useState(loadConversation);
  const [prompt, setPrompt] = useState("");
  const [language, setLanguage] = useState("en");
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [speakingMessageId, setSpeakingMessageId] = useState(null);
  const [inputNotice, setInputNotice] = useState("");
  const messageEnd = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    messageEnd.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages, isLoading]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        HISTORY_KEY,
        JSON.stringify(messages.slice(-MAX_HISTORY_MESSAGES)),
      );
    } catch (error) {
      console.warn("Could not save the assistant conversation for this session.", error);
    }
  }, [messages]);

  useEffect(() => () => {
    recognitionRef.current?.abort();
    window.speechSynthesis?.cancel();
  }, []);

  const sendMessage = async (
    text,
    {
      addUserMessage = true,
      retryErrorId = null,
      requestLanguage = language,
    } = {},
  ) => {
    const question = text.trim();
    if (!question || isLoading) return;
    if (question.length > 1990) {
      setInputNotice("Please shorten the question to 1,990 characters or less.");
      return;
    }

    setInputNotice("");
    setPrompt("");
    setMessages((current) => {
      const withoutRetriedError = retryErrorId
        ? current.filter((message) => message.id !== retryErrorId)
        : current;
      if (!addUserMessage) return withoutRetriedError;
      return [
        ...withoutRetriedError,
        {
          id: `user-${Date.now()}`,
          role: "user",
          text: question,
          language: requestLanguage,
        },
      ];
    });
    setIsLoading(true);

    try {
      const result = await sendChatMessage({
        message: `[lang=${requestLanguage}]\n${question}`,
        studentId: getStudentId(),
      });
      if (typeof result.answer !== "string" || !result.answer.trim()) {
        throw new Error("The assistant returned an empty answer.");
      }

      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          text: result.answer,
          sources: Array.isArray(result.sources) ? result.sources : [],
          language: requestLanguage,
        },
      ]);
    } catch (error) {
      console.error("Schobot assistant request failed:", error);
      const errorMessage = error instanceof Error
        ? error.message
        : "Please try again.";
      setMessages((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          text: `The scholarship assistant couldn't complete that response. ${errorMessage}`,
          sources: [],
          isError: true,
          retryQuestion: question,
          language: requestLanguage,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    void sendMessage(prompt);
  };

  const toggleVoiceInput = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setInputNotice("Voice input is not supported in this browser. You can type your question instead.");
      return;
    }

    window.speechSynthesis?.cancel();
    setSpeakingMessageId(null);
    setInputNotice("");

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = language === "hi" ? "hi-IN" : "en-IN";
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map((result) => result[0]?.transcript || "")
          .join(" ")
          .trim();
        if (!transcript) {
          setInputNotice("No speech was detected. Please try again or type your question.");
          return;
        }
        void sendMessage(transcript, { requestLanguage: language });
      };
      recognition.onerror = (event) => {
        const messagesByError = {
          "audio-capture": "No microphone was found. Connect a microphone or type your question.",
          "not-allowed": "Microphone permission was denied. Allow microphone access in your browser settings to use voice input.",
          "service-not-allowed": "The browser speech service is unavailable. You can type your question instead.",
          "no-speech": "No speech was detected. Please try again or type your question.",
        };
        setInputNotice(
          messagesByError[event.error]
            || "Voice input failed. Please try again or type your question.",
        );
      };
      recognition.onend = () => {
        if (recognitionRef.current === recognition) {
          recognitionRef.current = null;
        }
        setIsListening(false);
      };
      recognitionRef.current = recognition;
      setIsListening(true);
      recognition.start();
    } catch (error) {
      recognitionRef.current = null;
      setIsListening(false);
      setInputNotice(
        error.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow microphone access in your browser settings to use voice input."
          : "Could not start voice input. Please try again or type your question.",
      );
    }
  };

  const speakMessage = (message) => {
    const speech = window.speechSynthesis;
    const Utterance = window.SpeechSynthesisUtterance;
    if (!speech || !Utterance) {
      setInputNotice("Speech output is not supported in this browser.");
      return;
    }

    if (speakingMessageId === message.id) {
      speech.cancel();
      setSpeakingMessageId(null);
      return;
    }

    recognitionRef.current?.stop();
    speech.cancel();
    setInputNotice("");

    const isHindiResponse =
      message.language === "hi" || /[\u0900-\u097f]/u.test(message.text);
    const locale = isHindiResponse ? "hi-IN" : "en-IN";
    const languageCode = isHindiResponse ? "hi" : "en";
    const voices = speech.getVoices();
    const voice =
      voices.find((item) => item.lang.toLowerCase() === locale.toLowerCase())
      || voices.find((item) => item.lang.toLowerCase().startsWith(`${languageCode}-`));
    if (!voice) {
      setInputNotice(
        `No ${isHindiResponse ? "Hindi" : "English"} speech voice is available in this browser.`,
      );
      setSpeakingMessageId(null);
      return;
    }

    const utterance = new Utterance(message.text);
    utterance.lang = voice.lang || locale;
    utterance.voice = voice;
    utterance.rate = 0.96;
    utterance.onend = () => setSpeakingMessageId(null);
    utterance.onerror = (event) => {
      setSpeakingMessageId(null);
      if (event.error !== "canceled" && event.error !== "interrupted") {
        setInputNotice("Speech output could not be played. Try again or read the answer.");
      }
    };
    setSpeakingMessageId(message.id);
    speech.speak(utterance);
  };

  const retryMessage = (message) => {
    void sendMessage(message.retryQuestion, {
      addUserMessage: false,
      retryErrorId: message.id,
      requestLanguage: message.language || language,
    });
  };

  return (
    <main className="content-page assistant-page">
      <div className="page-heading">
        <p className="eyebrow">HERE TO HELP</p>
        <h1>Schobot AI Assistant</h1>
        <p className="page-subtitle">
          Ask questions about scholarships in English or Hindi.
        </p>
      </div>

      <section className="chat-card" aria-label="Schobot assistant chat">
        <header className="chat-card-header">
          <span className="chat-header-icon">
            <Icon name="spark" size={18} />
          </span>

          <div>
            <strong>Scholarship Assistant</strong>
            <span>
              <i /> Answers grounded in available scholarship records
            </span>
          </div>

          <label className="chat-language-control">
            <span>Answer language</span>
            <select
              aria-label="Answer language"
              onChange={(event) => {
                setLanguage(event.target.value);
                setInputNotice("");
              }}
              value={language}
            >
              <option value="en">English</option>
              <option value="hi">Hindi</option>
            </select>
          </label>
        </header>

        <div
          className="chat-transcript"
          aria-live="polite"
          aria-relevant="additions"
        >
          {messages.length > 0 ? (
            <p className="chat-date-label">THIS SESSION</p>
          ) : (
            <div className="chat-empty-state">
              <span className="chat-empty-icon">
                <Icon name="spark" size={24} />
              </span>
              <h2>How can I help with scholarships?</h2>
              <p>
                Ask about a scholarship, eligibility information, benefits or
                application documents. Answers use records available to Schobot.
              </p>
            </div>
          )}

          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              isLoading={isLoading}
              isSpeaking={speakingMessageId === message.id}
              message={message}
              onRetry={retryMessage}
              onSpeak={speakMessage}
            />
          ))}

          {isLoading && (
            <div className="chat-loading" role="status">
              <span className="chat-loading-dots" aria-hidden="true">
                <i /><i /><i />
              </span>
              Schobot is checking scholarship information...
            </div>
          )}

          <div ref={messageEnd} />
        </div>

        <div className="suggested-questions">
          <span>TRY ASKING</span>
          <div>
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                disabled={isLoading}
                onClick={() => void sendMessage(suggestion)}
                type="button"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>

        <ChatInput
          isListening={isListening}
          isLoading={isLoading}
          onChange={setPrompt}
          onSubmit={handleSubmit}
          onVoiceToggle={toggleVoiceInput}
          value={prompt}
        />

        {inputNotice && (
          <p className="chat-input-notice" role="status">
            {inputNotice}
          </p>
        )}

        <p className="chat-disclaimer">
          Answers are based on available scholarship records. Verify eligibility,
          application status and deadlines with the official scheme source.
        </p>
      </section>
    </main>
  );
}
