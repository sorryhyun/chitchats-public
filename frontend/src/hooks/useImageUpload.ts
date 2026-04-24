import { ChangeEvent, ClipboardEvent, useCallback, useState } from 'react';

export interface ImageData {
  data: string; // Base64 (no data: prefix)
  mediaType: string;
  preview: string; // Full data URL
}

export const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
export const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
export const MAX_IMAGES = 5;

function fileToImageData(file: File): Promise<ImageData> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve({
        data: result.split(',')[1],
        mediaType: file.type,
        preview: result,
      });
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function useImageUpload() {
  const [images, setImages] = useState<ImageData[]>([]);

  const addOne = useCallback(async (file: File) => {
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      alert('Please select a valid image file (PNG, JPEG, GIF, or WebP)');
      return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      alert('Image size must be less than 10MB');
      return;
    }
    setImages(prev => {
      if (prev.length >= MAX_IMAGES) {
        alert(`Maximum ${MAX_IMAGES} images allowed`);
        return prev;
      }
      return prev;
    });
    try {
      const data = await fileToImageData(file);
      setImages(prev => [...prev, data].slice(0, MAX_IMAGES));
    } catch (err) {
      console.error('Error converting image:', err);
      alert('Failed to process image');
    }
  }, []);

  const addMany = useCallback(async (files: FileList | File[]) => {
    const arr = Array.from(files);
    let remaining = 0;
    setImages(prev => {
      remaining = MAX_IMAGES - prev.length;
      return prev;
    });
    if (remaining <= 0) {
      alert(`Maximum ${MAX_IMAGES} images allowed`);
      return;
    }
    const valid = arr.slice(0, remaining).filter(file => {
      if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
        console.warn(`Skipping invalid file type: ${file.type}`);
        return false;
      }
      if (file.size > MAX_IMAGE_SIZE) {
        console.warn(`Skipping file too large: ${file.name}`);
        return false;
      }
      return true;
    });
    try {
      const newImages = await Promise.all(valid.map(fileToImageData));
      setImages(prev => [...prev, ...newImages].slice(0, MAX_IMAGES));
    } catch (err) {
      console.error('Error converting images:', err);
      alert('Failed to process some images');
    }
  }, []);

  const handleFiles = useCallback(
    (files: FileList | File[]) => {
      const arr = files instanceof FileList ? Array.from(files) : files;
      if (arr.length === 1) addOne(arr[0]);
      else if (arr.length > 1) addMany(arr);
    },
    [addOne, addMany],
  );

  const handleInputChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (files && files.length > 0) handleFiles(files);
      e.target.value = '';
    },
    [handleFiles],
  );

  const handlePaste = useCallback(
    (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      const imageFiles: File[] = [];
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile();
          if (file) imageFiles.push(file);
        }
      }
      if (imageFiles.length > 0) {
        e.preventDefault();
        handleFiles(imageFiles);
      }
    },
    [handleFiles],
  );

  const remove = useCallback((index: number) => {
    setImages(prev => prev.filter((_, i) => i !== index));
  }, []);

  const clear = useCallback(() => setImages([]), []);

  return {
    images,
    addOne,
    handleFiles,
    handleInputChange,
    handlePaste,
    remove,
    clear,
  };
}
