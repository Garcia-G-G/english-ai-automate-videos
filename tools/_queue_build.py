"""Helper: build a queue script from the narration plus the minimum metadata."""
import json, pathlib
Q = pathlib.Path('content/queue')

def edu(cat, tid, name, title, desc, hook, script, phrases, tip, cta, tags):
    d = {"type":"educational","video_title":title,"video_description":desc,"hook":hook,
         "full_script":script,"english_phrases":list(phrases.keys()),"translations":phrases,
         "tip":tip,"cta":cta,"hashtags":tags,
         "_meta":{"category":cat,"topic_id":tid,"video_type":"educational","model":"claude-opus-5"}}
    p=Q/'educational'; p.mkdir(parents=True,exist_ok=True)
    json.dump(d,open(p/f'{name}.json','w'),ensure_ascii=False,indent=2)

def tf(cat, tid, name, title, desc, statement, correct, expl, script, phrases, tags):
    d = {"type":"true_false","video_title":title,"video_description":desc,
         "statement":statement,"correct":correct,"explanation":expl,
         "full_script":script,"translations":phrases,"hashtags":tags,
         "_meta":{"category":cat,"topic_id":tid,"video_type":"true_false","model":"claude-opus-5"}}
    p=Q/'true_false'; p.mkdir(parents=True,exist_ok=True)
    json.dump(d,open(p/f'{name}.json','w'),ensure_ascii=False,indent=2)

def quiz(cat, tid, name, title, desc, question, options, correct, expl, script, phrases, tags):
    d = {"type":"quiz","video_title":title,"video_description":desc,
         "question":question,"options":options,"correct":correct,"explanation":expl,
         "full_script":script,"translations":phrases,"hashtags":tags,
         "_meta":{"category":cat,"topic_id":tid,"video_type":"quiz","model":"claude-opus-5"}}
    p=Q/'quiz'; p.mkdir(parents=True,exist_ok=True)
    json.dump(d,open(p/f'{name}.json','w'),ensure_ascii=False,indent=2)

def fb(cat, tid, name, title, desc, sentence, options, correct, translation, expl, script, tags):
    d = {"type":"fill_blank","video_title":title,"video_description":desc,
         "sentence":sentence,"options":options,"correct":correct,"translation":translation,
         "explanation":expl,"full_script":script,"hashtags":tags,
         "_meta":{"category":cat,"topic_id":tid,"video_type":"fill_blank","model":"claude-opus-5"}}
    p=Q/'fill_blank'; p.mkdir(parents=True,exist_ok=True)
    json.dump(d,open(p/f'{name}.json','w'),ensure_ascii=False,indent=2)

def voc(cat, tid, name, title, desc, vtitle, diff, pairs, script, tags):
    d = {"type":"vocabulary","video_title":title,"video_description":desc,"title":vtitle,
         "difficulty":diff,"pairs":[{"spanish":s,"english":e} for s,e in pairs],
         "full_script":script,"translations":{e:s for s,e in pairs},
         "english_phrases":[e for _,e in pairs],"hashtags":tags,
         "_meta":{"category":cat,"topic_id":tid,"video_type":"vocabulary","model":"claude-opus-5"}}
    p=Q/'vocabulary'; p.mkdir(parents=True,exist_ok=True)
    json.dump(d,open(p/f'{name}.json','w'),ensure_ascii=False,indent=2)

def pron(cat, tid, name, title, desc, word, phonetic, mistake, tip, translation, script, tags):
    d = {"type":"pronunciation","video_title":title,"video_description":desc,"word":word,
         "phonetic":phonetic,"common_mistake":mistake,"tip":tip,"translation":translation,
         "full_script":script,"hashtags":tags,
         "_meta":{"category":cat,"topic_id":tid,"video_type":"pronunciation","model":"claude-opus-5"}}
    p=Q/'pronunciation'; p.mkdir(parents=True,exist_ok=True)
    json.dump(d,open(p/f'{name}.json','w'),ensure_ascii=False,indent=2)
