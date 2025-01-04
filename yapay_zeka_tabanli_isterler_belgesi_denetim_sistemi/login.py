from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
from datetime import datetime
from nltk.tokenize import word_tokenize
from collections import Counter
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from translate import Translator
from nltk.tokenize import sent_tokenize
import nltk
import re
import json
import string
import zeyrek
import stanza

nltk.download('punkt')
# stanza.download('tr') (bir defa indirilmesi yeterli)

app = Flask('__name__')
app.secret_key = 'your-secret-key'

nlp = stanza.Pipeline('tr', processors='tokenize,ner', use_gpu=False)
morph_analyzer = zeyrek.MorphAnalyzer()

#MySQL Konfigürasyonları
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'dilara'
app.config['MYSQL_DB'] = 'flask_users'

mysql = MySQL(app)

# Yasak kelimelerin bulunduğu JSON dosyasını banned_words değişkenine at
with open('static/yasak_kelimeler.json', 'r', encoding='utf-8') as f:
    banned_words = json.load(f)['yasak_kelimeler']


# Kelimelerin yasaklı olup olmadığını kontrol et
def is_banned(word):
    for category in banned_words:
        if word in category['patterns']:
            return category['tag']
    return False

# Yasaklı kelimeleri kırmızı, gerisini turuncu olarak işaretle
def highlight_banned_words(sentence):
    words = word_tokenize(sentence)
    highlighted_sentence = ""
    found_banned = False
    redMassage = ''
    orangeMassage = ''

    for word in words:
        tag = is_banned(word.lower())
        if tag == 'yasak':
            highlighted_sentence += f'<span style="color:red">{word}</span> '
            found_banned = True
            redMassage = '• Cümle içerisinde kırmızı olarak işaretlenen kelime isterler cümlesinde olmaması gereken ifadedir.'
        elif tag is not False:
            highlighted_sentence += f'<span style="color:orange">{word}</span> '
            found_banned = True
            orangeMassage = '• Cümle içerisinde turuncu olarak işaretlenen kelime isterler cümlesinde olması uygun olmayan ifadedir.'
        else:
            highlighted_sentence += f'{word} '

    if not found_banned:
        return (highlighted_sentence.strip(), False,redMassage,orangeMassage)
    else:
        return (highlighted_sentence.strip(), True,redMassage,orangeMassage)


# Cümle sonunda nokta var mı kontrol et
def check_dot(sentence):
    if sentence and re.search(r'\.\s*$', sentence) is None: #r'[^\w\s]$'
        return "• İsterler cümlesi nokta ile bitmelidir. Lütfen cümleyi kontrol ediniz." 
    else:
        return False 

# Kelime tekrarı konrtol edilir
def check_word_repetition(sentence):
    words = [word.lower() for word in nltk.wordpunct_tokenize(sentence) if word.isalnum()]
    word_counts = Counter(words)
    repeated_words = {word: count for word, count in word_counts.items() if count > 1}
    
    if repeated_words:
        output = "• Cümlede "
        for word, count in repeated_words.items():
            output += f"' {word}' kelimesi {count} kez,"
        output = output.rstrip(",") + " geçmektedir. İsterler cümlesinde kelime tekrarı fazla olmamalıdır."
        return output
    else:
        return False

# Cümlede duygu analizi yapar, negatif ise uyarı verir
def sentiment_Vader(sentence):
    translated_text = translate_text(sentence)
    sid = SentimentIntensityAnalyzer()
    extend_vader_lexicon(sid)
    over_all_polarity = sid.polarity_scores(translated_text)
    print(over_all_polarity)
    if over_all_polarity['compound'] <= -0.05:
        return '• Cümle negatif anlam taşımaktadır. İsterler dokümanında genellikle negatif cümleler olması tercih edilmez.'
    else:
        return False

#Özel kelimeler ekleyerek duygu analizi fonksiyonunu geliştirme
def extend_vader_lexicon(analyzer):
    new_words = {
        "not": -2.0
    }
    analyzer.lexicon.update(new_words)

# Cümle duygu analizi için İngilizce'ye çevrilir
def translate_text(text, src_lang='tr', dest_lang='en'):
    translator = Translator(from_lang=src_lang, to_lang=dest_lang)
    translation = translator.translate(text)
    return translation

# Virgülden önce fiil var mı?
def check_verb_before_comma(sentence):
    counter = 0
    clauses = sentence.split(',')
    
    for i in range(1, len(clauses)):
        clause = clauses[i - 1].strip()
        words = clause.split()
        
        if words:  
            last_word = words[-1]
            analyses = morph_analyzer.analyze(last_word)
            if analyses:  
                for analysis in analyses:
                    if 'Verb' in str(analysis):
                        counter += 1
                        break
    if counter >=1:
        return f'• Birden fazla cümlenin birleştirilmesiyle oluşmuş cümleler isterler dokümanında olmamalıdır. \nBu cümle ile {counter+1} adet cümle birleştirilmiştir.'
    else:
        return False
    
# Teknik ifade kontrolü
def check_technical_terms(sentence):
    doc = nlp(sentence)
    technical_terms = [ent.text for ent in doc.ents if ent.type in ['ORGANIZATION', 'PRODUCT']]
    
    if technical_terms:
        return "• İsterler cümlesinde çözüm içeren ifadeler bulunmamalıdır. Cümle içerisinde tespit edilen ifadeler: " + ", ".join(technical_terms)
    else:
        return False
    
# Cümle tam bir cümle mi? (Özne-yüklem içeriyor mu?)
def checkFullSentence(sentence):
    analysis = morph_analyzer.analyze(sentence)
    has_verb = any('Verb' in word_analysis for sentence_analysis in analysis for word_analysis in sentence_analysis)

    if has_verb is True and len(analysis) > 1:
        return False
    else:
        return '• Yazılan cümle tam bir cümle değildir! Cümlede mutlaka yüklem bulunmalıdır.'

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        pwd = request.form['password']
        cur = mysql.connection.cursor()
        cur.execute(f"select username, password from tbl_users where username = '{username}'")
        user = cur.fetchone()
        cur.close()
        if user and pwd == user[1]:
            session['username'] = user[0]
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error ='Yanlış kullanıcı adı veya şifre girdiniz..')
    return render_template ('login.html')

@app.route('/home', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        text = request.form['sentence']
        if not text: 
            message = '<span style="color:red"> Kontrol edilmesini istediğiniz isterler cümlesini giriniz. </span>'
            return render_template('home.html', message=message)

        sentences = sent_tokenize(text)
        results = []
        checkEND = True

        for sentence in sentences:
            highlighted_sentence, checkTF, redMessage, orangeMessage = highlight_banned_words(sentence)
            check_dott = check_dot(sentence)
            word_repetition = check_word_repetition(sentence)
            sentimentVader = sentiment_Vader(sentence)
            checkVerbBeforeComma = check_verb_before_comma(sentence)
            checkTechnicalTerms = check_technical_terms(sentence)
            checkFull = checkFullSentence(sentence)

            checkEND = [checkTF, check_dott,word_repetition,sentimentVader, checkVerbBeforeComma, checkTechnicalTerms, checkFull]

            if all(check is False for check in checkEND):
                endResult = '<span style="color:blue"> Yazılan cümle isterler dokümanı için uygundur. </span>'
            else:
                endResult = ''

            sentence_result = {
                'sentence': highlighted_sentence,
                'endResult' : endResult,
                'check_dott': check_dott,
                'word_repetition': word_repetition,
                'sentiment_Vader': sentimentVader,
                'checkVerbBeforeComma': checkVerbBeforeComma,
                'checkTechnicalTerms': checkTechnicalTerms,
                'redMessage': redMessage,
                'orangeMessage': orangeMessage,
                'checkFull':checkFull
                }
            results.append(sentence_result)

        return render_template('home.html', results=results)
    return render_template('home.html')


@app.route('/kayit', methods=['GET','POST'])
def kayit():
    if request.method == 'POST':
        username = request.form['username']
        pwd = request.form['password']
        join_date = datetime.now().strftime('%Y-%m-%d')
        email = request.form['email']

        cur = mysql.connection.cursor()

        try: 
            cur.execute(f"insert into tbl_users (username, password, join_date, email) values ('{username}', '{pwd}', '{join_date}', '{email}')")
            mysql.connection.commit()
            flash('Kayıt işlemi başarıyla tamamlandı!', 'success')
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Kayıt sırasında bir hata oluştu: {str(e)}', 'danger')
            return redirect(url_for('kayit'))
        cur.close() 
    return render_template('kayitSayfasi.html')

@app.route('/cikis')
def cikis():
    session.pop('username', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)

