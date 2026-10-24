"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Image as ImageIcon,
  Upload,
  Plus,
  Trash2,
  Star,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  Loader2,
  ExternalLink,
  RefreshCw,
  Link as LinkIcon,
  X,
} from "lucide-react";
import { api, resolveMediaUrl } from "@/lib/api/client";

export interface ListingPhotoManagerProps {
  primaryImageUrl: string;
  images: string[];
  onChange: (primaryImageUrl: string, images: string[]) => void;
  maxImages?: number;
  maxFileSizeBytes?: number; // Default: 5MB
  listingType?: "vehicle" | "part" | "catalogue";
  listingId?: string;
  label?: string;
  title?: string;
  description?: string;
}

interface UploadingItem {
  tempId: string;
  tempUrl: string;
  filename: string;
  status: "uploading" | "success" | "error";
  errorMessage?: string;
}

const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];
const ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"];
const DEFAULT_MAX_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB

export default function ListingPhotoManager({
  primaryImageUrl,
  images = [],
  onChange,
  maxImages = 10,
  maxFileSizeBytes = DEFAULT_MAX_SIZE_BYTES,
  listingType = "vehicle",
  listingId,
  label,
  title = "Listing Photos & Gallery",
  description,
}: ListingPhotoManagerProps) {
  const displayTitle = title || label || "Listing Photos & Gallery";
  const [error, setError] = useState<string>("");
  const [successMsg, setSuccessMsg] = useState<string>("");
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [uploadingQueue, setUploadingQueue] = useState<UploadingItem[]>([]);
  const [brokenImages, setBrokenImages] = useState<Record<string, boolean>>({});

  // URL fallback states
  const [showUrlInput, setShowUrlInput] = useState<boolean>(false);
  const [manualUrl, setManualUrl] = useState<string>("");

  // Inline replace states
  const [replaceIndex, setReplaceIndex] = useState<number | null>(null);
  const [replaceUrl, setReplaceUrl] = useState<string>("");

  // File input refs
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const replaceFileInputRef = useRef<HTMLInputElement | null>(null);

  // Keep track of blob URLs for memory cleanup
  const activeBlobUrlsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    return () => {
      // Revoke all created browser object URLs on unmount
      activeBlobUrlsRef.current.forEach((objUrl) => {
        try {
          URL.revokeObjectURL(objUrl);
        } catch {
          // Ignore
        }
      });
      activeBlobUrlsRef.current.clear();
    };
  }, []);

  const createBlobUrl = (file: File): string => {
    const url = URL.createObjectURL(file);
    activeBlobUrlsRef.current.add(url);
    return url;
  };

  const revokeBlobUrl = (url: string) => {
    if (url.startsWith("blob:")) {
      try {
        URL.revokeObjectURL(url);
        activeBlobUrlsRef.current.delete(url);
      } catch {
        // Ignore
      }
    }
  };

  const validateFile = (file: File): string | null => {
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    const hasValidExt = ALLOWED_EXTENSIONS.includes(ext);
    const hasValidMime = ALLOWED_MIME_TYPES.includes(file.type.toLowerCase()) || file.type === "";

    if (!hasValidExt && !hasValidMime) {
      return `"${file.name}" has an unsupported format. Please upload JPG, PNG, or WebP.`;
    }

    if (file.size > maxFileSizeBytes) {
      const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
      const limitMB = (maxFileSizeBytes / (1024 * 1024)).toFixed(0);
      return `"${file.name}" exceeds the ${limitMB}MB size limit (file is ${sizeMB}MB).`;
    }

    return null;
  };

  const handleFilesSelected = async (selectedFiles: FileList | File[]) => {
    setError("");
    setSuccessMsg("");
    const fileList = Array.from(selectedFiles);

    if (fileList.length === 0) return;

    // Check maximum total images
    const currentTotal = images.length + uploadingQueue.length;
    if (currentTotal + fileList.length > maxImages) {
      const remainingSlots = Math.max(0, maxImages - currentTotal);
      setError(
        `Cannot add ${fileList.length} photo(s). Maximum limit of ${maxImages} photos per listing (${remainingSlots} slot(s) remaining).`
      );
      return;
    }

    // Validate all files first
    for (const file of fileList) {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }
    }

    // Process and upload each file
    let currentImages = [...images];
    let currentPrimary = primaryImageUrl;

    for (const file of fileList) {
      const tempId = Math.random().toString(36).substring(2, 9);
      const previewUrl = createBlobUrl(file);

      const queueItem: UploadingItem = {
        tempId,
        tempUrl: previewUrl,
        filename: file.name,
        status: "uploading",
      };

      setUploadingQueue((prev) => [...prev, queueItem]);

      try {
        const uploadRes = await api.marketplace.uploadImage(file, {
          listingType,
          listingId,
        });

        // Store the returned media URL (relative /media/... or absolute URL)
        const savedUrl: string = uploadRes.url || uploadRes.relative_url || uploadRes.absolute_url || "";

        // Clean up preview object URL
        revokeBlobUrl(previewUrl);

        currentImages = [...currentImages, savedUrl];
        if (!currentPrimary) {
          currentPrimary = savedUrl;
        }

        onChange(currentPrimary, currentImages);

        // Remove from uploading queue
        setUploadingQueue((prev) => prev.filter((item) => item.tempId !== tempId));
        setSuccessMsg(`"${file.name}" uploaded successfully.`);
      } catch (err: unknown) {
        revokeBlobUrl(previewUrl);
        setUploadingQueue((prev) =>
          prev.map((item) =>
            item.tempId === tempId
              ? {
                  ...item,
                  status: "error",
                  errorMessage: err instanceof Error ? err.message : "Upload failed.",
                }
              : item
          )
        );
        setError(
          `Failed to upload "${file.name}": ${err instanceof Error ? err.message : "Network error."}`
        );
      }
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFilesSelected(e.target.files);
    }
    // Reset input value to allow selecting the same file again if desired
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files);
    }
  };

  const handleRemoveImage = (indexToRemove: number) => {
    setError("");
    setSuccessMsg("");
    const removedUrl = images[indexToRemove];
    revokeBlobUrl(removedUrl);

    const updatedImages = images.filter((_, idx) => idx !== indexToRemove);

    let updatedPrimary = primaryImageUrl;
    if (primaryImageUrl === removedUrl) {
      updatedPrimary = updatedImages.length > 0 ? updatedImages[0] : "";
    }

    onChange(updatedPrimary, updatedImages);
    if (replaceIndex === indexToRemove) {
      setReplaceIndex(null);
      setReplaceUrl("");
    }
  };

const handleSetPrimary = (url: string) => {
  setError("");
  const updatedImages = [...images];
  if (!updatedImages.includes(url)) {
    updatedImages.unshift(url);
  }
  onChange(url, updatedImages);
};

  const handleMove = (fromIndex: number, toIndex: number) => {
    if (toIndex < 0 || toIndex >= images.length) return;
    const updated = [...images];
    const [moved] = updated.splice(fromIndex, 1);
    updated.splice(toIndex, 0, moved);
    onChange(primaryImageUrl, updated);
  };

  const handleReplaceWithFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (replaceIndex === null || !e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    e.target.value = "";

    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    try {
      const uploadRes = await api.marketplace.uploadImage(file, {
        listingType,
        listingId,
      });

      const newUrl: string = uploadRes.url || uploadRes.relative_url || uploadRes.absolute_url || "";
      const oldUrl = images[replaceIndex];
      revokeBlobUrl(oldUrl);

      const updated = [...images];
      updated[replaceIndex] = newUrl;

      let updatedPrimary = primaryImageUrl;
      if (primaryImageUrl === oldUrl) {
        updatedPrimary = newUrl;
      }

      onChange(updatedPrimary, updated);
      setReplaceIndex(null);
      setReplaceUrl("");
      setSuccessMsg(`Photo replaced successfully with "${file.name}".`);
    } catch (err: unknown) {
      setError(`Failed to replace photo: ${err instanceof Error ? err.message : "Upload error."}`);
    }
  };

  const handleExecuteReplaceUrl = (index: number) => {
    setError("");
    const trimmed = replaceUrl.trim();
    if (!trimmed) {
      setError("Please provide a valid replacement URL.");
      return;
    }

    const oldUrl = images[index];
    revokeBlobUrl(oldUrl);
    const updated = [...images];
    updated[index] = trimmed;

    let updatedPrimary = primaryImageUrl;
    if (primaryImageUrl === oldUrl) {
      updatedPrimary = trimmed;
    }

    onChange(updatedPrimary, updated);
    setReplaceIndex(null);
    setReplaceUrl("");
    setSuccessMsg("Photo URL updated.");
  };

  const handleAddManualUrl = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setError("");
    setSuccessMsg("");

    if (images.length >= maxImages) {
      setError(`Maximum limit of ${maxImages} images reached.`);
      return;
    }

    const trimmed = manualUrl.trim();
    if (!trimmed) {
      setError("Please enter a valid image URL.");
      return;
    }

    if (images.includes(trimmed)) {
      setError("This photo URL is already in the gallery.");
      return;
    }

    const updatedImages = [...images, trimmed];
    const updatedPrimary = primaryImageUrl && images.includes(primaryImageUrl) ? primaryImageUrl : updatedImages[0];
    onChange(updatedPrimary, updatedImages);
    setManualUrl("");
    setSuccessMsg("Photo URL added to gallery.");
  };

  const isAtCapacity = images.length + uploadingQueue.length >= maxImages;

  return (
    <div className="space-y-4">
      {/* Header & Limits */}
      <div>
        <div className="flex items-center justify-between">
          <label className="block text-slate-800 font-bold text-xs flex items-center gap-1.5">
            <ImageIcon className="w-4 h-4 text-amber-500" />
            <span>{displayTitle}</span>
            <span className="text-[10px] text-slate-400 font-normal">
              ({images.length}/{maxImages} photos)
            </span>
          </label>
          <span className="text-[10px] text-slate-400">JPG, PNG, WebP (max 5 MB each)</span>
        </div>
        {description && <p className="text-[11px] text-slate-500 mt-0.5">{description}</p>}
      </div>

      {/* Hidden File Inputs */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileInputChange}
        accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
        multiple
        className="hidden"
      />
      <input
        type="file"
        ref={replaceFileInputRef}
        onChange={handleReplaceWithFile}
        accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
        className="hidden"
      />

      {/* Drag & Drop Upload Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => {
          if (!isAtCapacity && fileInputRef.current) {
            fileInputRef.current.click();
          }
        }}
        className={`relative border-2 border-dashed rounded-2xl p-6 transition-all duration-200 text-center cursor-pointer flex flex-col items-center justify-center gap-2 ${
          isAtCapacity
            ? "border-slate-200 bg-slate-50 cursor-not-allowed opacity-60"
            : isDragging
            ? "border-amber-500 bg-amber-500/10 scale-[1.01]"
            : "border-slate-300 hover:border-amber-500 hover:bg-slate-50/80 bg-white"
        }`}
      >
        <div className="w-12 h-12 rounded-full bg-amber-500/10 text-amber-600 flex items-center justify-center">
          <Upload className="w-6 h-6 text-amber-500" />
        </div>
        <div className="space-y-1">
          <p className="text-xs font-bold text-slate-800">
            {isAtCapacity
              ? `Maximum photo limit (${maxImages}) reached`
              : "Click to upload photos or drag and drop"}
          </p>
          <p className="text-[11px] text-slate-500">
            Select one or multiple images from your computer (JPEG, PNG, WebP up to 5 MB)
          </p>
        </div>
        <button
          type="button"
          disabled={isAtCapacity}
          onClick={(e) => {
            e.stopPropagation();
            if (fileInputRef.current) fileInputRef.current.click();
          }}
          className="mt-1 px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-all shadow-sm flex items-center gap-1.5 disabled:opacity-50"
        >
          <Upload className="w-3.5 h-3.5 text-amber-400" />
          <span>Upload Photos from Computer</span>
        </button>
      </div>

      {/* URL fallback accordion toggle */}
      <div className="flex items-center justify-between text-[11px] pt-1">
        <button
          type="button"
          onClick={() => setShowUrlInput((prev) => !prev)}
          className="text-slate-500 hover:text-slate-800 font-medium flex items-center gap-1 transition-colors"
        >
          <LinkIcon className="w-3 h-3 text-slate-400" />
          <span>{showUrlInput ? "Hide manual URL input" : "Or paste an existing image URL..."}</span>
        </button>
        <span className="text-slate-400">
          {images.length} of {maxImages} slots used
        </span>
      </div>

      {/* Manual URL Input Bar */}
      {showUrlInput && (
        <form
          onSubmit={handleAddManualUrl}
          className="flex flex-col sm:flex-row gap-2 p-3 bg-slate-50 rounded-xl border border-slate-200"
        >
          <input
            type="url"
            placeholder="Paste public image URL (e.g. https://...)"
            value={manualUrl}
            onChange={(e) => {
              setManualUrl(e.target.value);
              if (error) setError("");
            }}
            disabled={isAtCapacity}
            className="flex-1 px-3 py-2 text-xs bg-white border border-slate-200 rounded-lg focus:outline-none focus:border-amber-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isAtCapacity || !manualUrl.trim()}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold rounded-lg transition-all disabled:opacity-50 flex items-center justify-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5 text-amber-400" />
            <span>Add URL</span>
          </button>
        </form>
      )}

      {/* Feedback Alerts */}
      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-xl flex items-center justify-between gap-2 animate-fadeIn">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => setError("")}
            className="p-1 text-rose-500 hover:text-rose-700"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {successMsg && (
        <div className="p-2.5 bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs rounded-xl flex items-center justify-between gap-2 animate-fadeIn">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
            <span>{successMsg}</span>
          </div>
          <button
            type="button"
            onClick={() => setSuccessMsg("")}
            className="p-1 text-emerald-500 hover:text-emerald-700"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Gallery Grid */}
      {(images.length > 0 || uploadingQueue.length > 0) && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 pt-1">
          {/* Active Saved/Uploaded Images */}
          {images.map((url, index) => {
            const isPrimary = url === primaryImageUrl || (index === 0 && !primaryImageUrl);
            const isBroken = brokenImages[url];
            const isReplacing = replaceIndex === index;
            const resolvedSrc = resolveMediaUrl(url);

            return (
              <div
                key={`${url}-${index}`}
                className={`group relative rounded-2xl border transition-all overflow-hidden bg-slate-900 flex flex-col ${
                  isPrimary
                    ? "border-amber-500 ring-2 ring-amber-500/20 shadow-md"
                    : "border-slate-200 hover:border-slate-400"
                }`}
              >
                {/* Thumbnail */}
                <div className="relative aspect-[4/3] bg-slate-950 flex items-center justify-center overflow-hidden">
                  {!isBroken ? (
                    <img
                      src={resolvedSrc}
                      alt={`Listing Photo ${index + 1}`}
                      onError={() => {
                        setBrokenImages((prev) => ({ ...prev, [url]: true }));
                      }}
                      className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                  ) : (
                    <div className="p-3 text-center text-slate-500 space-y-1">
                      <AlertCircle className="w-6 h-6 text-rose-400 mx-auto" />
                      <span className="text-[10px] block leading-tight text-slate-400">Broken Image</span>
                    </div>
                  )}

                  {/* Primary Badge */}
                  {isPrimary && (
                    <div className="absolute top-2 left-2 px-2 py-0.5 rounded-full bg-amber-500 text-slate-950 text-[9px] font-black uppercase tracking-wider shadow flex items-center gap-1 z-10">
                      <Star className="w-2.5 h-2.5 fill-slate-950" />
                      <span>Primary</span>
                    </div>
                  )}

                  {/* Order Tag */}
                  <span className="absolute top-2 right-2 px-1.5 py-0.5 rounded bg-black/60 backdrop-blur-sm text-white text-[9px] font-mono z-10">
                    #{index + 1}
                  </span>

                  {/* Quick Remove Button */}
                  <button
                    type="button"
                    onClick={() => handleRemoveImage(index)}
                    title="Remove Photo"
                    className="absolute bottom-2 right-2 p-1.5 rounded-lg bg-black/70 hover:bg-rose-600 text-white transition-colors opacity-90 sm:opacity-0 group-hover:opacity-100 z-10"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>

                  {/* Full Preview External Link */}
                  <a
                    href={resolvedSrc}
                    target="_blank"
                    rel="noreferrer"
                    title="Open full size"
                    className="absolute bottom-2 left-2 p-1.5 rounded-lg bg-black/70 hover:bg-slate-700 text-white transition-colors opacity-90 sm:opacity-0 group-hover:opacity-100 z-10"
                  >
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>

                {/* Card Controls Footer */}
                <div className="p-2 bg-slate-900 border-t border-slate-800 text-[10px] space-y-1.5">
                  <div className="flex items-center justify-between gap-1">
                    {!isPrimary ? (
                      <button
                        type="button"
                        onClick={() => handleSetPrimary(url)}
                        className="text-[10px] font-bold text-amber-400 hover:text-amber-300 flex items-center gap-1 transition-colors"
                      >
                        <Star className="w-3 h-3" />
                        <span>Set Primary</span>
                      </button>
                    ) : (
                      <span className="text-[10px] font-bold text-slate-400">Main Photo</span>
                    )}

                    <div className="flex items-center gap-1 ml-auto">
                      <button
                        type="button"
                        onClick={() => handleMove(index, index - 1)}
                        disabled={index === 0}
                        title="Move left"
                        className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-30"
                      >
                        <ChevronLeft className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleMove(index, index + 1)}
                        disabled={index === images.length - 1}
                        title="Move right"
                        className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-30"
                      >
                        <ChevronRight className="w-3 h-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (isReplacing) {
                            setReplaceIndex(null);
                            setReplaceUrl("");
                          } else {
                            setReplaceIndex(index);
                            setReplaceUrl(url);
                          }
                        }}
                        title="Replace photo"
                        className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
                      >
                        <RefreshCw className="w-3 h-3" />
                      </button>
                    </div>
                  </div>

                  {/* Inline Replace Options */}
                  {isReplacing && (
                    <div className="pt-2 border-t border-slate-800 space-y-1.5 animate-fadeIn">
                      <p className="text-[9px] text-slate-400 font-semibold uppercase tracking-wider">
                        Replace Photo:
                      </p>
                      <div className="flex gap-1">
                        <button
                          type="button"
                          onClick={() => {
                            if (replaceFileInputRef.current) {
                              replaceFileInputRef.current.click();
                            }
                          }}
                          className="w-full py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded text-[10px] flex items-center justify-center gap-1"
                        >
                          <Upload className="w-2.5 h-2.5" />
                          <span>Upload File</span>
                        </button>
                      </div>

                      <div className="space-y-1 pt-1">
                        <input
                          type="url"
                          placeholder="Or paste replacement URL"
                          value={replaceUrl}
                          onChange={(e) => setReplaceUrl(e.target.value)}
                          className="w-full px-2 py-1 text-[10px] bg-slate-950 border border-slate-700 text-white rounded focus:outline-none focus:border-amber-500"
                        />
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => {
                              setReplaceIndex(null);
                              setReplaceUrl("");
                            }}
                            className="px-2 py-0.5 text-slate-400 hover:text-white"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => handleExecuteReplaceUrl(index)}
                            className="px-2 py-0.5 bg-slate-700 hover:bg-slate-600 text-white font-bold rounded"
                          >
                            Save URL
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Currently Uploading Items in Queue */}
          {uploadingQueue.map((item) => (
            <div
              key={item.tempId}
              className="relative rounded-2xl border border-amber-500/50 bg-slate-900 overflow-hidden flex flex-col animate-pulse"
            >
              <div className="relative aspect-[4/3] bg-slate-950 flex items-center justify-center overflow-hidden">
                <img
                  src={item.tempUrl}
                  alt={item.filename}
                  className="w-full h-full object-cover opacity-50"
                />
                <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-1.5 p-2 text-center">
                  {item.status === "uploading" ? (
                    <>
                      <Loader2 className="w-6 h-6 text-amber-400 animate-spin" />
                      <span className="text-[10px] text-white font-medium">Uploading...</span>
                    </>
                  ) : item.status === "error" ? (
                    <>
                      <AlertCircle className="w-6 h-6 text-rose-400" />
                      <span className="text-[10px] text-rose-300 font-medium">Upload failed</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-6 h-6 text-emerald-400" />
                      <span className="text-[10px] text-emerald-300 font-medium">Uploaded</span>
                    </>
                  )}
                </div>
              </div>
              <div className="p-2 bg-slate-900 text-[10px] text-slate-400 truncate">
                {item.filename}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Secure Storage Note */}
      <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-[11px] text-slate-600 flex items-start gap-2">
        <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
        <div className="space-y-0.5">
          <p className="font-semibold text-slate-800">Direct Computer Uploads Enabled</p>
          <p className="text-slate-500 leading-relaxed">
            Photos are saved directly to secure DriverXtra media storage with automatic validation.
            The primary photo serves as the thumbnail across the buyer marketplace and saved items list.
          </p>
        </div>
      </div>
    </div>
  );
}
