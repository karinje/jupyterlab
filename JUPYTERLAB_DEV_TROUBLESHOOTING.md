# JupyterLab Development Troubleshooting Guide

## ⚠️ CRITICAL: The Caching Problem Pattern

**This pattern happened MULTIPLE times during development:**

1. Make code changes to extension
2. Run `npm run build`
3. Changes don't appear in JupyterLab
4. Spend time debugging code when the real issue is **CACHED FILES**

## 🔥 The Nuclear Option - When Changes Don't Appear

When your code changes aren't reflected, follow this escalating sequence:

### Level 1: Basic Clean
```bash
cd /Users/sanjaykarinje/git/jupyterlab/dev_mode
npm run build
```

### Level 2: Clean Dev Mode
```bash
cd /Users/sanjaykarinje/git/jupyterlab/dev_mode
rm -rf static/*
npm run build
```

### Level 3: Clean Extension Cache
```bash
cd /Users/sanjaykarinje/git/jupyterlab/dev_mode
rm -rf node_modules/@jupyterlab/chat*
npm run build
```

### Level 4: Nuclear Clean (Use When Nothing Else Works)
```bash
cd /Users/sanjaykarinje/git/jupyterlab/dev_mode
rm -rf static/*
rm -rf node_modules/@jupyterlab/chat*
npm run build
```

### Level 5: Full Nuclear (Last Resort)
```bash
cd /Users/sanjaykarinje/git/jupyterlab
npm run clean:slate
# If this fails, proceed to manual cleanup below
```

## 🚨 When Dev Environment Breaks

**Symptoms:** `jupyter lab` command not found or fails to start

**Root Cause:** Aggressive cleaning broke the development setup

**Fix:**
```bash
cd /Users/sanjaykarinje/git/jupyterlab
pip install -e .
```

**Then test:**
```bash
jupyter lab --dev-mode --no-browser
```

## 🔍 Verification Commands

**Check if your changes are compiled:**
```bash
# Search for your debug messages in compiled files
find static -name "*.js" -exec grep -l "your debug message" {} \;

# Search for old class names that should be removed
find static -name "*.js" -exec grep -l "ChatWidget" {} \;
```

**If searches return files, your changes aren't compiled! Go nuclear.**

## 📋 The Complete Development Workflow

### Making Extension Changes:

1. **Edit source files** (`packages/chat/src/*`)

2. **Build packages first:**
   ```bash
   cd /Users/sanjaykarinje/git/jupyterlab
   npm run build:packages
   ```

3. **Build dev mode:**
   ```bash
   cd dev_mode
   npm run build
   ```

4. **Verify changes compiled:**
   ```bash
   find static -name "*chat*" -exec grep -l "your new debug message" {} \;
   ```

5. **Refresh JupyterLab page** (don't restart server unless needed)

### When Changes Don't Appear:

⚠️ **DON'T DEBUG CODE FIRST** - Check caching issues first!

1. **Check if compiled:** Use verification commands above
2. **If not compiled:** Use Nuclear Option sequence
3. **If still not working:** Full dev environment reset

## 🏗️ Build Process Understanding

### File Locations:
- **Source:** `packages/chat/src/`
- **Compiled packages:** `packages/chat/lib/`
- **Dev mode compiled:** `dev_mode/static/`
- **Final served files:** What browser loads

### Build Chain:
```
Source → npm run build:packages → npm run build (dev_mode) → Browser
```

**Each step can cache!** If changes don't appear, cache exists somewhere in this chain.

## 🛠️ Common Error Patterns

### 1. TypeScript Errors After Major Changes
```bash
# Fix: Clean and rebuild packages first
cd /Users/sanjaykarinje/git/jupyterlab
npm run build:packages
cd dev_mode
npm run build
```

### 2. Module Not Found Errors
```bash
# Check if extension exports changed
# Fix: Update index.ts exports to match what exists
```

### 3. Extension Not Loading
```bash
# Check browser console for errors
# Often: TypeScript compilation failed silently
```

### 4. Old Widget/Component Still Appearing
```bash
# This is ALWAYS a caching issue
# Go nuclear immediately, don't debug code
```

## 🚀 Starting JupyterLab Commands

**Standard development:**
```bash
cd /Users/sanjaykarinje/git/jupyterlab
jupyter lab --dev-mode --no-browser
```

**With specific working directory:**
```bash
cd /Users/sanjaykarinje/git/jupyterlab
jupyter lab --dev-mode --notebook-dir=/path/to/work/directory
```

**Auto-open browser:**
```bash
cd /Users/sanjaykarinje/git/jupyterlab
jupyter lab --dev-mode
```

## 💡 Key Learnings

1. **Caching is the #1 problem in JupyterLab development**
2. **Always verify compilation before debugging code**
3. **When in doubt, go nuclear with cache clearing**
4. **Dev environment can break after aggressive cleaning**
5. **Multiple levels of caching exist (packages, dev_mode, static)**
6. **Browser refresh ≠ cache clearing**

## 🔄 Quick Reset Sequence

When nothing works and you need to start fresh:

```bash
# 1. Clean everything
cd /Users/sanjaykarinje/git/jupyterlab/dev_mode
rm -rf static/* node_modules/@jupyterlab/chat*

# 2. Rebuild packages
cd /Users/sanjaykarinje/git/jupyterlab
npm run build:packages

# 3. Rebuild dev mode
cd dev_mode
npm run build

# 4. Fix dev environment if broken
cd /Users/sanjaykarinje/git/jupyterlab
pip install -e .

# 5. Start JupyterLab
jupyter lab --dev-mode --no-browser
```

---

**Remember:** When changes don't appear, it's caching 99% of the time, not your code!
