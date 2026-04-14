"use client";

import { useRef, useState } from "react";
import { Editor } from "@tiptap/react";
import { BubbleMenu } from "@tiptap/react/menus";
import { uploadFile, uploadPersonalFile } from "../../lib/api";

interface EditorToolbarProps {
  editor: Editor | null;
  workspaceId?: string | null;
}

function ToolbarButton({
  onClick,
  isActive,
  title,
  children,
}: {
  onClick: () => void;
  isActive?: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onMouseDown={(e) => {
        e.preventDefault();
        onClick();
      }}
      className={`px-2 py-1 rounded text-sm font-medium transition-colors ${
        isActive
          ? "bg-white/15 text-white"
          : "text-white/70 hover:bg-white/10 hover:text-white"
      }`}
      title={title}
    >
      {children}
    </button>
  );
}

function Separator() {
  return <div className="w-px h-4 bg-white/20 mx-0.5" />;
}

export default function EditorToolbar({ editor, workspaceId }: EditorToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !editor) return;
    setUploading(true);
    try {
      const result = workspaceId
        ? await uploadFile(workspaceId, file)
        : await uploadPersonalFile(file);
      if (result.content_type.startsWith("image/")) {
        editor.chain().focus().setImage({ src: result.url, alt: result.name }).run();
      } else {
        editor.chain().focus().setLink({ href: result.url }).insertContent(result.name).run();
      }
    } catch {
      // Storage may not be configured
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  if (!editor) return null;

  return (
    <>
      <BubbleMenu
        editor={editor}
      >
        <div className="flex items-center gap-0.5 px-1.5 py-1 rounded-lg bg-[#1a1a2e] border border-white/10 shadow-xl">
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBold().run()}
          isActive={editor.isActive("bold")}
          title="Bold (Ctrl+B)"
        >
          <strong>B</strong>
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleItalic().run()}
          isActive={editor.isActive("italic")}
          title="Italic (Ctrl+I)"
        >
          <em>I</em>
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleStrike().run()}
          isActive={editor.isActive("strike")}
          title="Strikethrough"
        >
          <s>S</s>
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleCode().run()}
          isActive={editor.isActive("code")}
          title="Inline code"
        >
          <code className="text-xs">&lt;/&gt;</code>
        </ToolbarButton>

        <Separator />

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
          isActive={editor.isActive("heading", { level: 1 })}
          title="Heading 1"
        >
          H1
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          isActive={editor.isActive("heading", { level: 2 })}
          title="Heading 2"
        >
          H2
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
          isActive={editor.isActive("heading", { level: 3 })}
          title="Heading 3"
        >
          H3
        </ToolbarButton>

        <Separator />

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          isActive={editor.isActive("bulletList")}
          title="Bullet list"
        >
          &bull;
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          isActive={editor.isActive("orderedList")}
          title="Ordered list"
        >
          1.
        </ToolbarButton>

        <Separator />

        <ToolbarButton
          onClick={() => {
            const url = prompt("Enter URL:");
            if (url) {
              editor.chain().focus().setLink({ href: url }).run();
            }
          }}
          isActive={editor.isActive("link")}
          title="Add link"
        >
          Link
        </ToolbarButton>
        {editor.isActive("link") && (
          <ToolbarButton
            onClick={() => editor.chain().focus().unsetLink().run()}
            title="Remove link"
          >
            Unlink
          </ToolbarButton>
        )}

        <Separator />

        <ToolbarButton
          onClick={() => {
            const url = prompt("Image URL:");
            if (url) {
              editor.chain().focus().setImage({ src: url }).run();
            }
          }}
          title="Insert image by URL"
        >
          Img
        </ToolbarButton>
        <ToolbarButton
          onClick={() => fileInputRef.current?.click()}
          title="Upload image or file"
        >
          {uploading ? "..." : "Upload"}
        </ToolbarButton>
        </div>
      </BubbleMenu>

      {/* Hidden file input for uploads */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf,.doc,.docx,.txt,.csv"
        className="hidden"
        onChange={handleImageUpload}
      />
    </>
  );
}
