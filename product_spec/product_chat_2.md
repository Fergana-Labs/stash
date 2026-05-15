Speaker A: All right, here we go. Let me just. Yeah, let's talk through the so far. Okay, first bullet point. Pages cannot be shared, but you can share a stash with a page or page on it.
Speaker B: Agreed.
Speaker A: Privacy lives at the level of the stash also.
Speaker B: Agreed. And we have this weird thing where you want to make something private, you add it to a stash that is a private stash. And a private stash that's. Any stash with a number of users is like less than the whole company. The private stash literally, literally cannot be added or.
Speaker A: Sorry, no.
Speaker B: Page in a private level stash can be added to a public level stash.
Speaker A: Yep. Basically becomes this, like. Becomes this. Partition. Basically.
Speaker B: That's the word that makes it make sense.
Speaker A: Yeah. Partition.
Speaker B: It's quite enough.
Speaker A: Okay.
Speaker B: Which is not crazy. I think notion essentially does this too.
Speaker A: Yeah. Link. And the key to think here is that this only needs to make sense to like a user, which is like an ant who cannot see the whole system. As long as that user ant makes sense, the whole system is fine. If it's pretty weird reason about it. Cool. No links. Links in the wiki for now. And it's not a wiki, it's a file system. And that makes it more sense. Makes it more sense to agents as well. Yeah, that makes sense.
Speaker B: Okay.
Speaker A: Sessions have predefined MECE folders. I guess they would be called around things like who the user uploaded it and like the date or something.
Speaker B: Yep. This is purely organizational. It's not user configurable at all.
Speaker A: Yes. It's just the UI thing. There's probably worth a blog post by me about recognition versus recall and like news feeds and stuff. But that's sort of the rationale.
Speaker B: Yeah.
Speaker A: Behind that.
Speaker B: I like news feeds so much. Why don't we just add a newsfeed?
Speaker A: We have a newsfeed.
Speaker B: Okay, gotcha.
Speaker A: In discover or newsfeed thing. Right. I guess we didn't talk about what it is, same or separate, but we do have some notion of that. Okay. There's one we're talking about who can add or remove sessions or pages to a stash. And it's a different question of existing edits to a page. And the answer to this is there's another weird separate thing which is if you're an external user and you have edit access to a stash, you can add shit.
Speaker B: You can create a page, you can
Speaker A: create a page, but that page does
Speaker B: not live in a workspace. It's like an external shared page and it lives only in the stash and it's like a totally weird thing where normally pages don't explicitly belong to a stash. Except in this case.
Speaker A: Yes. And then maybe in V1 we can do this thing where it's just a button that's at the workspace, but maybe not for now.
Speaker B: Yeah, that's easy. You just choose a subfolder to put it under.
Speaker A: Yeah. Oh, there's another thing that's not on this list which talk about which is in these sort of hooks that automatically push transcripts, the session history. You should be allowed to choose a default stash that it gets loaded into.
Speaker B: Yeah, this is news to me, but I agree.
Speaker A: Yeah. Okay, next bullet. I agree. Integrations aren't in V0, but it's a high priority for V1. Do you agree with that?
Speaker B: I agree too.
Speaker A: Okay, sounds good. Is there a better name than workspace for where everything gets dumped?
Speaker B: Maybe.
Speaker A: I mean, I think workspace makes the most sense to people because it matches existing SaaS paradigms.
Speaker B: I don't know. Anything from bubble. Say you should not make up your own words if you can help it.
Speaker A: Okay.
Speaker B: Guess what they call database rules.
Speaker A: Oh, I remember this. Well, I don't remember. I remember.
Speaker B: Yeah, that was the worst word of all time. We had to, like, talk about things in technical documentation. Like it was in keyword, and everyone's like, wait, so what is that thing? And you're like, no, no, key thing means something very specific in bubble.
Speaker A: Okay. Maybe the lesson is your core product can be a new thing, like stash.
Speaker B: Sure, yeah. I mean, a stash. A stash is fine because it's genuinely not. Does not have a name already. In CS parlance, there's no name for
Speaker A: this kind of thing. Okay, so keeping workspaces, that's fine. Co. Oh, yeah, I think you mentioned that. We don't have sleep time. Compute. Do you still want handout documents from this hash?
Speaker B: How about no, just keep it simple and then put that in V1.
Speaker A: Okay, sounds good. That's fine. Okay, last bullet point. I agree with the issue of editing a page when it's live published, but. Oh, yeah, yeah. Like you have this whole thing in the specular lab where, like, if I try to edit a page that's been published or it's public like the cli, or like there's a UI for it that's like, are you sure I shut
Speaker B: this up last night.
Speaker A: Yeah.
Speaker B: What do you think about that?
Speaker A: It feels intuitively feels clunky, but.
Speaker B: Well, here's some other options that I wrote up when I was Thinking of this, the other options are one, no editing. It feels weird because like, then you're gonna fork.
Speaker A: Yeah.
Speaker B: And like if you have a page that you want to keep editing, there's gonna be a fork of it running them. And another option is that you can always allow edits, which is weird because maybe it's a bit of a hook gun. Like you could share an external document and then edit it by accident.
Speaker A: Well, I think that's fine. That's how like anything works. Like Google Docs notion, like they don't warn you, they just expect you to know it's been shared. Or do we expect that to be like, how about this?
Speaker B: Why don't we just have a. Instead of putting up a gate, why don't we say like it's very clear in the ui this is a shared. Like there's a little like that just shared or something.
Speaker A: Okay.
Speaker B: And then we get the best of both worlds.
Speaker A: That sounds good. And then I guess maybe if you want to edit it as AI, we tell you first, AI should be able
Speaker B: to see from its interaction with the cli this is a shared file and we trust it to use its own judgment to not. Not that Claude's particularly good at this, but use its own judgment to not like break something that's in broad.
Speaker A: Okay, I think that's fair. I think the intuition for this because I think I like that comes from just like the number of like consultant projects where we do care a lot about internal versus external or client interactions. This is almost never a problem.
Speaker B: Really?
Speaker A: Yeah, like people just know like whether this has been shared or not and it's fine. Like.
Speaker B: Well, that's convincing.
Speaker A: Yeah. Okay, cool. Let's see some other things we talked about. I have here. Oh, okay. I guess we already talked about this, but essentially my concern of like the group Gmail label tag situation and people not liking me see structures. It's like a concern I have.
Speaker B: Well, here's what I'll say. That is like a checkmate argument against this. Like I think if people use sashes as mece things, like we're actually still fine, but still a valuable product.
Speaker A: Fair. Okay. Yeah, I guess like Google Drive is like this too, right? Like you can use Google Drive as just this like general mess thing, but you can also just create footers if you want.
Speaker B: You could make it your notion thing. I don't think you should because it's really slow and just lacks a bunch of nice ui. But technically you could have a file system where the doc's in there.
Speaker A: Like you could use Google Drive like Dropbox, but it's bad. Like, I wouldn't want to.
Speaker B: I. I do use Google Drive like Dropbox.
Speaker A: Wait, really?
Speaker B: Well, how do you use Dropbox? Dropbox is just a place where you randomly upload miscellaneous shit, right?
Speaker A: No, I use Dropbox as like, because of the sync feature.
Speaker B: Yeah.
Speaker A: I use it as like a core part of my file system on a computer. Okay.
Speaker B: Yeah, I don't do that. And I would certainly not do that with Google Drive.
Speaker A: Yeah, Google Drive feels weird. It's kind of similar to what we're talking about here where you have this like, shared with me thing that's different from like, my Google Drive. And I'm just like, where the fuck is anything?
Speaker B: I'm shared drives, which different than shared folders.
Speaker A: Yeah. And I have, like, no idea what anything is.
Speaker B: Their information hierarchy is a complete mess. I think any big organization is doomed to have a product that's confusing because there's just too many orgs and they all want to do their own project.
Speaker A: Yeah.
Speaker B: But yeah, like, they have like five different features to do the same use case for every use case.
Speaker A: Yeah. I think a good product principle here is like, it's okay if that's a mess in the future, but for now there has to be like, very simple, clean concepts that user can anchor to early product ever.
Speaker B: Is this product granola? Because it was just unbelievably, like, lacking in abstractions. It's literally just a button you can press that records you. Meaning they didn't make workspaces, they didn't make groups, they didn't make collaboration. Like, it's literally just a button you press. I was like, thank God. Like, I know this product.
Speaker A: Thank you. Or I guess maybe a better way to phrase my. My nuanced view on this is that granola today has a bunch of random attractions. It is fine because if you want to use them, you can get deep into it, but it's not required for you to use the product. I think that's what we need to keep very clear as a principle is if you use the product today or in like two years, your initial onboarding value delivery system has to be very clean.
Speaker B: I agree. I think I'd be anti example. This is like gcp. In order to do even the easiest thing, it's like, first get access. Like, if you want to make a file, you need to get access to file. Right. Which means you need to make an access group, and your access group needs to be owned by an admin group. And these all need to live in a group group and like you have to create like 17 different things just to like create a file.
Speaker A: Yeah. I think Google Docs is actually not bad at this because I don't need to worry about all this hierarchy thing that's kind of confusing. Press create doc and you share.
Speaker B: That's. That's. I use them exclusively as a place to make expendable docs like the not expendable document like one op doc. Like the thing I read last night.
Speaker A: I think Notion is kind of in between. You kind of need to buy into the notion system for it to actually be useful to you. Notion sort of in between.
Speaker B: But they want you to do like a bit of a file system.
Speaker A: Yeah. Or yeah. I think it's weird. It's not quite a file system. It's like a wiki but it's in between the wiki and the file system. It's its own unique thing.
Speaker B: What makes a wiki? Oh not 100% files.
Speaker A: They have links and more importantly pages are folders as well. Through links.
Speaker B: Yeah, that's like weird. Like that's, that's like neither a wiki nor a file system.
Speaker A: Did you see that Notion also made gave your agent the cli or rather you could use the CLI to access their agent somehow.
Speaker B: Yeah, I saw that. Yeah, I think that's great. I still think we, we rate them cuz they're down.
Speaker A: Okay. Okay. So I think that's. Yeah, this is a concern. I think it's relatively okay as long as. Basically as long as like there's a really clean view on what the user can do to get initial value. Like complicated things are. Okay. Okay, let's see. Okay. And I guess the only other overarching point I was making is like I think I noticed that you framed a stash as a convenience or like a flimsy sort of view. Yeah, I. So this is not I guess a product specific thing. Like there's no tangible like thing I'm recommending here. It's more like a philosophy that I want to talk about which is I think a stash is the content that makes this whole thing work. And I guess this is related to our content of like you would think that a black hole search is fine and I think that's not sufficient. But here's sort of a couple reasons. I listed four but like reasons why I think a stash is important as like a more like fully fleshed concept than just like a convenience. Basically the first is that it creates anchoring effects for teams around what's important and what's not. Like in the world where you have so much data and everything's contradictory and like things that's modified, what is the anchor point of truth? I would want to argue that we want users to think of a stash and a thing that's in a stash that's curated as that source of truth and everything doesn't go into black hole as larger context. But stash is sort of that truth value thing. That's sort of the first argument. The second is that sort of agents and humans in general crave structure for retrieval of things. Like there's a way in which you have pinned objects or a common whatever for a reason. It's because there are things that you just go to often again and again. And so Sash income sense should become that like common pathway, that like sort of neural in a way. If you do something too many times, your brain creates a like a pathway for it. The stash sort of should become that.
Speaker B: I have a question. Do you want users going to Stash like every day or like every five minutes? Or do you want it to work even if you never go to stash.com?
Speaker A: up to them.
Speaker B: Sorry?
Speaker A: Up to them.
Speaker B: What do you want though? What's a better user?
Speaker A: You mean in terms of going to the UI versus pure cli? Yeah.
Speaker B: Or like more specifically, I'm imagining one way you could use stash is that you don't even know it exists. All you know is that your agents are working better.
Speaker A: I guess my take on that is
Speaker B: it's like super memory.
Speaker A: Yeah. I guess my take on is that we will not get good users. If that. That is the problem.
Speaker B: I think you're right.
Speaker A: It's too bad.
Speaker B: But yeah, super memory, even if it does make your agents better, no one gives a.
Speaker A: Because it doesn't make it better by enough for you to notice.
Speaker B: And that too. Yeah. And arguably it makes it worse, honestly, because I don't know how good the retrieval isn't. Super memory.
Speaker A: Yeah. I guess the important thing is that even if it made it like 20 times better, the feedback loop inherently to memory, because it's about long term things, is so long that you're not going to have that dopamine effect to like spread and like whatever you're not going to get. Yeah. So I think we want from like a lot of reasons we want users to like be in stash, like in the ui. We want to form the habit. Right. And the trigger action. Habit loop.
Speaker B: Yeah. Pressing X all the time.
Speaker A: Yeah.
Speaker B: Browser URL search bar.
Speaker A: That's why I think like Serno sharing is like a really good example of that trigger action reward loop. What are some other examples of this?
Speaker B: What's the trigger and what's the action? What's the reward?
Speaker A: In that case, the trigger is like, I need to share something externally, like HTML page, just information. Or maybe internally I need to share it with you. I need to share some view of you. The action is I create a stash. Right. And the reward is, oh, like this is easy. Like this is like, you know, seamless experience. What are some other trigger action rewards? I need to find something like, oh, I figured something I forgot something.
Speaker B: These are all like the use cases that we talk about. Like I want to know what I did yesterday.
Speaker A: Yeah.
Speaker B: I asked my agent. Bam. It magically knows.
Speaker A: Yeah, I mean what I kind of wanted today was like I was trying to find that book recommendation. Yeah. I was like, where the fuck is that book? I know I saved it somewhere.
Speaker B: You ever like. I mean, I guess it literally came from a coding engine transcript. So that's easy. Like you just figure find the conversation where the agent recommended a book.
Speaker A: Yeah. Well, what I tried to do is I had this like external bookmark manager I like pay for. I tried to find it in there, but it was a mess.
Speaker B: It was like a png, right?
Speaker A: Png.
Speaker B: Like you're looking for an image screenshot that you took, right?
Speaker A: Oh no, I saved the book rack as a link.
Speaker B: Okay.
Speaker A: Yeah, the screenshot though, I know I took a png. I just could not find it. There's just no way I could. Also, why is no one built like just OCR on all your images? Like this feels like a thing.
Speaker B: Yeah. It's pretty unbelievable how bad Apple's search is. I think Raycast might do that. Honestly, like I see are in your images.
Speaker A: Yeah, well, I'm going to check because I. I find, I think about once a week I have this case where I. I know I have a screenshot somewhere with some text on it I cannot find.
Speaker B: Takes five minutes, but it finds it every time. So I'll just OCR every screenshot.
Speaker A: I have thousands of screenshots.
Speaker B: That might take a while.
Speaker A: Like the way I use screenshots is kind of how I guess you use Google Docs.
Speaker B: Like just disposable.
Speaker A: Disposable. They all go on the desktop. And every once in a while I'm like, why do I have 2000 documents on my desktop? I put them onto a folder and I call it a day.
Speaker B: That might Be done for that.
Speaker A: Yeah, I use screenshots in my roughly the same way. Honestly, I have a ton. Also screenshots is one of the reasons why I think I can never switch off of a Mac. Like that screenshot plus airdrop combination is such a smooth experience and I use it so much like either my laptop or to the phone or vice versa.
Speaker B: Gotcha. Yeah, that is it.
Speaker A: I use it like.
Speaker B: How on earth do you even do that on a Windows computer? Like you email yourself.
Speaker A: Yeah, it's so painful.
Speaker B: I have to go all the way over to Google just to get it under my computer. It's two feet away.
Speaker A: Yeah, yeah, yeah. Anyway, so the other argument. So number three I was talking about was. Oh yeah, this is kind of an example of generative ui. The whole point of generative UI is that like, there's some stable, like, background just state of the world that the AI knows about and it surfaces like random UI to you on demand. That's like useful to you in the moment.
Speaker B: Certainly. I agree.
Speaker A: Stash is like a really good, is an example of that. It's not really generative ui, but it's the same type of like, pattern.
Speaker B: I mean, it, yeah, like you can imagine the future where it's like a stash homepage and the stash homepage is just generative. Generative UI slapped on top of the contents of said stash.
Speaker A: Yeah, but it's not really ui, it's more like a generative like view. But it's the same idea. Right. It's just like the interface is unstable, but the background knowledge is stable.
Speaker B: Exactly. I think that's great. There's some great places for it.
Speaker A: Yeah. And clearly the future is going in this direction, so. Oh, yeah, I think the last one is just the thing we talked about where like, I think, yeah, basically glean is not the right mental model for
Speaker B: us, which is this clean is like a black hole.
Speaker A: Black hole plus search. Yeah, all right.
Speaker B: I mean, I'll respond. I, I, I don't think of stashes as a flimsy thing at all. Actually, I completely agree with you and I'd like you to tell me where in that document I wrote about the Moja, because I don't think I, I did.
Speaker A: Oh, okay. I might have misread. Let me just double check.
Speaker B: I, I think stashes are completely critical of this product and the central thing of this product.
Speaker A: Okay, I might have misread something.
Speaker B: Well, okay, someone. Okay.
Speaker A: Oh, okay. I think I misread you. You were saying that publishing is mostly aesthetic thing yes yeah I read that as like a stash is mostly aesthetic
Speaker B: thing but maybe publish. I guess it's the same thing right like hitting publish on the stash it just like makes that stash public and also
Speaker A: yeah I've send you a link that you can type yeah my understanding that we talked about yesterday is that like V0 that it is just like it just makes it public kind of Google Docs which makes it public and then maybe we have a notion like a concept of like forking published later but we don't need to worry about
Speaker B: that now yeah I think yeah maybe there's something where like when you hit publish it like gets published to a special site and it looks very professional or something but that's totally a later on feature yeah and shouldn't matter for
Speaker A: now okay cool I think we went through all those I think we're mostly yeah we're more aligned I'm going to.