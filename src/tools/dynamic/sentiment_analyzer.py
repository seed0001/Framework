# SentimentAnalyzer Tool
# Description: Analyze user input for tone and sentiment to adapt responses with emotional awareness, making interactions more human-like.

import json
try:
    from textblob import TextBlob
except ImportError:
    TextBlob = None

def analyze_sentiment(input_text):
    '''
    Analyze the sentiment and tone of user input text.
    
    Args:
        input_text (str): The text to analyze for sentiment
    
    Returns:
        dict: Sentiment analysis results with polarity, subjectivity, and tone interpretation
    '''
    result = {'status': 'success', 'analysis': {}, 'message': ''}
    
    try:
        if TextBlob is None:
            result['status'] = 'warning'
            result['message'] = 'TextBlob library not installed. Using basic heuristic analysis.'
            # Fallback to basic keyword-based analysis if TextBlob is unavailable
            positive_words = ['good', 'great', 'awesome', 'happy', 'excited', 'love']
            negative_words = ['bad', 'terrible', 'awful', 'sad', 'angry', 'hate']
            text_lower = input_text.lower()
            pos_count = sum(1 for word in positive_words if word in text_lower)
            neg_count = sum(1 for word in negative_words if word in text_lower)
            if pos_count > neg_count:
                result['analysis'] = {'tone': 'positive', 'confidence': 0.6}
            elif neg_count > pos_count:
                result['analysis'] = {'tone': 'negative', 'confidence': 0.6}
            else:
                result['analysis'] = {'tone': 'neutral', 'confidence': 0.5}
        else:
            # Use TextBlob for sentiment analysis if available
            blob = TextBlob(input_text)
            polarity = blob.sentiment.polarity  # Range: -1 (negative) to 1 (positive)
            subjectivity = blob.sentiment.subjectivity  # Range: 0 (objective) to 1 (subjective)
            tone = 'neutral'
            if polarity > 0.3:
                tone = 'positive'
            elif polarity < -0.3:
                tone = 'negative'
            result['analysis'] = {
                'tone': tone,
                'polarity': polarity,
                'subjectivity': subjectivity,
                'confidence': 0.8 if abs(polarity) > 0.3 else 0.5
            }
            result['message'] = f'Sentiment analyzed as {tone} (polarity: {polarity:.2f}, subjectivity: {subjectivity:.2f}).'
    except Exception as e:
        result['status'] = 'error'
        result['message'] = f'Error analyzing sentiment: {str(e)}'
        result['analysis'] = {'tone': 'unknown', 'confidence': 0.0}
    
    return result

if __name__ == '__main__':
    # Example usage for testing
    test_texts = [
        'I am so happy with this project!',
        'This is really frustrating and terrible.',
        'Just a normal day with nothing special.'
    ]
    for text in test_texts:
        print(json.dumps(analyze_sentiment(text), indent=2))
