## V0 Stash Product Vision

This is our opinionated vision of how work is gonna get done in the future. So in a Stash Workspace, there are basically three things:

1. Sessions
   1. This is a dump of all of your agent’s chat transcripts and their outputs. This also includes any “temporary” non-code file that was created by the agent as part of its thinking (like a [PLAN.md](http://plan.md/))
   2. Sessions have some metadata: timestamp, which human kicked off the run, what coding agent it was (eg Henry’s Codex on GPT-5.5 ultra high thinking), and other stuff.
2. Filesystem
   1. This is just a filesystem. It’s like notion except AI can navigate it way better because to the agent, it looks like a real filesystem, has much better navigation utilities, and because it allows html. But under the hood, we could make it a db for performance reasons. We keep things as llm-legible as possible, so no weird notion-isms like “a page is made out of blocks” or “pages can have subpages”
   2. Humans can create a page.
3. Stashes
   1. This is a **new thing**. It didn’t exist before 2026, but we’re betting that it’s going to be a totally fundamental unit of getting work done as agents produce more and more information. It is a combination of sessions and filesystem pages. 
   2. Stashes can be published. Publishing them just means they’re made public and also the UI hands you over a link that you can use to give to anyone to share the Stash with them. When you publish, you are asked whether you want to share to the “discover”page.
   3. Your workspace can have Stashes created from pages within your workspace, as well as *external stashes* from outside your workspace. These are meant to function as *matrix kung fu-style cartridges* of information. Where do you get external stashes? Well, if you view a stash that’s not yours, then there will be a button that says “add to my workspace” and if you click it, then that stash will be added to your workspace

Product Requirements:

1. Users can easily see what Pages and Sessions are in a Stash, and you can also easily see which Stashes a given Page and Session is in.
   1. In the UI, sessions will be organized by sorted by day -> user for ease of readibility
2. There is beautiful UI to view a Page and a Session in the webapp
3. There is a beautiful sidebar UI to view the filetree of Pages, and the user- and time- ordered display of Sessions
4. There is the ability to search Pages, Sessions, and Stashes. You can limit a search to a certain Page or Folder, or a certain Stash, or “internal only” (no external stashes). 
5. In the product, you can easily create a stash by manually selecting which pages and sessions will go into it. Furthermore, you can easily ask your agent to create a stash, and it will be able to find the right pages and sessions to include in it.
6. Collaboration
   1. A Stash Workspace can have members in it. An admin can invite you to a workspace. You’re an admin if you made the workspace, or if another admin set you as an admin.
   2. When you’re in Stash, which workspace you’re in is clearly visible in the top left of the screen. 
   3. Sessions are default uploaded to the workspace visible to everyone in the workspace, but you can also change their privacy to be yourself only, or a certain group only. This is mediated by a Stash.
   4. If you publish a stash, you get a public-facing link to it. And that stash is publicly-viewable.
7. Privacy
   1. Privacy is mediated by a Stash. To any user, a Stash can appear to be workspace, private, public. 
      1. A workspace stash is a stash that everyone in the workspace can see. This is the default kind of stash. A workspace stash can also be shared with other people.
      2. A private stash is a stash that only certain people-including potentially people outside your workspace!- can see. A private stash is “cordoned off” from the rest of the workspace in that the pages and sessions in this stash cannot be included in any workspace- or public- stashes.
      3. A public stash is a stash that anyone in the world can see. 
   2. A Stash is absolutely the only way that privacy of files (eg workspace, public, private) is mediated. 
   3. All files default to “workspace” unless they’re in a stash that would give different permissions.
   4. Edit permissions must be at least as strict as view permissions, but can be stricter.
8. We have a beautiful and elegant CLI + MCP that allows AI to take almost any action on a Stash Workspace that a human can take, including CRUD on Pages, Sessions, and Stashes. The only thing an AI cannot do via CLI/MCP is edit the list of workspace members.
9. The homepage when you first get into a workspace is a newsfeed. It’s some combination of a “discover” page, recent sessions, and (something else?)
10. There is an “Activity” page that shows a summary of recent work in this workspace

Notes:

1. We expect a common usage pattern around publish to be: “write a new page specifically for the purposes of publishing it in a stash to share externally”

Open Questions:

1. What’s on the user’s homepage? A newsfeed? Alternatively, we could copy notion and make it the “workspace homepage”.
   1. A: Newsfeed
2. Is newsfeed/discover in scope for v0?
   1. A: Yes
3. Can the UI only display one workspace at a time?
   1. Yes, it’s like Slack
4. Do we have “requests to join” in v0?
   1. No not needed
5. Should a “table” be a separate type of page? Or can a page have a table in it?
   1. Yes its a separate type of page analogous to .csv.
   2. No a table cannot have a page in it because that’s annoying to agents
6. Can pages have subpages? Do we have folders?
   1. (1) no (2) yes

Glossary:

1. A **Stash Workspace** is the top level unit of this product. Everything lives in it. Closest comp is a Slack Workspace
2. A **Session** is a transcript of a coding agent session, along with any artifacts it generated along the way (eg [PLAN.md](http://plan.md/))
   1. An **Artifact** is the term for a file that is attached to a Session because it was generated during that session. 
3. A **Page** is any node in the **Files**. Tab We support these types of pages: html, markdown, any kind of file, any kind of image. There is an ugly exception to the rule that Pages live in the Filesystem, called “shared pages”. This is used when external collaborators add a page to a Stash.
4. A **Folder** is where Pages can live in the files section.
5. A **Stash** is our primary novel invention. It’s a generalization of a “tag”. It’s the most important part of the product. It’s a combination of Sessions and Pages. We think it will be the best way to share information with collaborators in the next few years, as more and more of the valuable information created by agents lives in Session transcripts. 
   1. The three permission states for a stash are “public”, “private”, and “workspace”
   2. A stash can be **published**. This is mostly aesthetic, it just means that we (1) make it public (2) give the user a Sharable link. But you can totally do all these things without ever hitting the publish button. it’s UI syntactic sugar for “make this stash public and give me the sharing link for it”. “Published” isn’t a separate permission state of a stash. The three permission states are “public” “private”, and “workspace”
   3. An **External Stash** is just any Stash that was added to a Workspace by the “Add to Workspace” button rather than by natively making it inside the workspace.
      1. Is this a reference or a fork? A fork!
   4. A Stash is absolutely the only way that privacy of files (eg workspace, public, private) is mediated. 

FAQ

1. Q: How do we handle privacy? 
   1. Privacy is mediated by Stashes.
2. Q: Can pages be published?
   1. No, only stashes. 
3. Q: Is there a concept of tagging?
   1. Nope! I mean, except in the sense that Stashes our are versions of tags
4. Q: Are there workspaces?
   1. Yes! A stash workspace is a combination of Sessions, “Files” Pages, and Stashes
5. Q: Is there a concept of “views”?
   1. Yes, but we’re calling them “Stashes” now
6. Q: When you edit a stash, does the underlying page get edited?
   1. Yep, if you edit a page included in a stash, then the stash will reflect that change. 
   2. You can only edit pages in a stash if you have edit permission on that stash.
7. Q: Can a user be a member of more than one Stash Workspace?
   1. Yeah, it’s like Slack
8. Q: Do we expect that a given bit of information will typically live in more than one stash?
   1. It totally could! And that’s fine. The same underlying page could be used in a bunch of stashes
9. Q: Does every stash need to live in a workspace?
   1. Yes! It does. But you can share a stash to other workspaces.
10. Q: Is a github repo meant to be uploading to only one stash workspace?
    1. Yes. We won’t prevent you from streaming transcripts to several workspaces, but that’s weird.
11. Q: Is a stash workspace meant to have only one github repo?
    1. No, you can have several. Eg: /frontend, /backend
12. Q: Is a Stash Live or a Snapshot?
    1. Live! 
13. Q: Wait, so when you add an external Stash to your workspace, is that a live thing that the author can edit at any time?
    1. Yep!
14. Q: Does a stash have version history? Does a filesystem have version history?
    1. Nope! Not in v0 at least.
15. Q: How do things get added to a stash workspace?
    1. Three ways:
       1. From the transcript upload hook
       2. From an agent manually doing it via CLI or MCP
       3. From a human manually doing it via UI
16. Q: What are we going to integrate with? Slack? Granola? Drive?
    1. Literally nothing. For v0 that is. Obviously this should be a fast follow but let’s just get the core thing up and running first.
17. Q: If the agent creates a page, who is the owner of that page?
    1. Who said pages had owners?
18. Q: Do sessions include files that were *edited* as part of the coding agent run, or just ones that it creates? What about .tsx files? Like real, new codebase files.
    1. Sessions should include everything! Even .tsx!
19. Can a page be shared, or only a stash?
    1. Only a stash 
20. Does privacy live at the tag level or the stash level?
    1. Stash level. In fact, there is no such thing as tags.
21. Should we have a wiki?
    1. No! We should actually have a filesystem. And we should not have *links* in the filesystem. We don’t need them and a filesystem is overall more intuitive to AI than a wiki.
22. In terms of UI design, how are Sessions displayed?
    1. We organize them first by Date, and then by User
23. Who can add/remove pages in a Stash? 
    1. Okay, this one’s a bit ugly ngl. If you are a member of a workspace that a Stash comes from, and you have edit permissions on that Stash, then you can add pages. If you are not a member of a workspace that a Stash comes from, you can *still* have edit access, and you can create new pages. But the new pages that you create are special type of page called *shared pages* which live directly in the Stash rather than anywhere in the workspace where the Stash originates.
    2. This isn’t the greatest thing ever, but 
24. Is there a better name than workspace that we can use?
    1. No
25. What about a generated orientation document? Is that in scope for v0?
    1. No
26. What happens if you try to edit a page that is inside a published stash?
    1. You will be able to successfully edit the page, without any “be careful” warnings of any kind.
27. Q: Isn’t it bad if users try to use stashes in a many-to-one way because they’re used to many-to-one systems like filesystems?
    1. Nope! If people exclusively used stashes in a many-to-one way (i.e. no page is ever in more than one stash at the same time) that’s fine. Like, we’re still a valuable product for those people.
28. If one Page belongs to multiple Stashes with different privacy levels, what wins: most permissive, most restrictive, or per-Stash context?
    1. If a page is in a private stash, it cannot be in a workspace or public stash.
    2. If a page is in a workspace stash, and a public stash, it is public.
29. Can you configure which stashes your sessions from your repo stream to by default?
    1. Yes!
30. Is “add to workspace” a reference or a clone?
    1. A reference!

## Not in Scope for V0

- Uploading anything besides coding agent session transcripts and their associated artifacts to the session view. We acknowledge that in future versions, we might want to support uploading slack convos, granola transcripts, etc.
- Agents maintaining the filesystem sleep-time compute, in any way. No curator agent whatsoever.
- “Favoriting” a Stash
- Version history for a stash
- Version history for the filesystem
- Any integrations of any kind
  - Integrations should be a super fast follow though
- A generated orientation document
- Onboarding
  - Our product says “Hey, paste this into your claude code” 
  - When it’s pasted, you see your session magically show up in stash OR it lets people upload an html and that will magically show up in your stash.

Appendix

Here are some product principles we will never betray:

1. All transcripts can just go into a magic black hole, you don’t need to route them yourself.
2. You can easily find information that you’re looking for by searching for it with a search bar
3. Agents can write pages
4. It's easy to share information with people
