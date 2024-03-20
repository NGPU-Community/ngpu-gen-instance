# -*- coding: utf-8 -*-
import langid

def detect_language(text):
    lang, confidence = langid.classify(text)
    return lang, confidence

def main():
    text = "你好，Hello，こんにちは"
    #text = "hello"
    language, confidence = detect_language(text)

    print(f"The detected language is: {language} with confidence: {confidence}")

if __name__ == "__main__":
    main()