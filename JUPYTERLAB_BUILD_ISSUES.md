# JupyterLab Production Build Issues with Local Workspace Dependencies

## 📋 **Problem Summary**

**Issue**: JupyterLab's production build (`jupyter lab build`) fails when extensions have local workspace dependencies that reference each other.

**Error**:
```
➤ YN0035: │ @jupyterlab/chat@npm:~4.1.0: The remote server failed to provide the requested resource
➤ YN0035: │   Response Code: 404 (Not Found)
➤ YN0035: │   Request Method: GET
➤ YN0035: │   Request URL: https://registry.yarnpkg.com/@jupyterlab%2fchat
```

**Current Status**: ❌ **UNRESOLVED** - Production build fails, dev-mode works perfectly

---

## 🏗️ **Our Architecture**

```
packages/
├── chat/                    # Core library (@jupyterlab/chat)
│   ├── src/
│   ├── package.json
│   └── ...
└── chat-extension/          # JupyterLab extension (@jupyterlab/chat-extension)
    ├── src/
    ├── package.json         # depends on "@jupyterlab/chat": "^4.1.0"
    └── ...
```

**This architecture follows JupyterLab conventions** (like `@jupyterlab/notebook` + `@jupyterlab/notebook-extension`)

---

## 🔍 **Root Cause Analysis**

### **How JupyterLab Build Process Works**

1. **Packs each extension** → Creates `jupyterlab-chat-extension-4.1.0.tgz`
2. **Creates staging workspace** → Isolated environment at `/mambaforge/share/jupyter/lab/staging/`
3. **Installs packed extension** → Runs `npm install jupyterlab-chat-extension-4.1.0.tgz`
4. **Resolves dependencies** → Sees `"@jupyterlab/chat": "^4.1.0"` in packed extension
5. **Looks for dependency** → Goes to npm registry, gets 404 ❌

### **The Fundamental Problem**

- **Staging workspace is isolated** from your development workspace
- **Packed extension references `@jupyterlab/chat` as published package**, not local
- **No workspace configuration carries over** to the staging build process
- **yarn/npm treats it as registry dependency**, not workspace dependency

---

## 🧪 **What We Tried (All Failed)**

### **1. Install Local Dependencies**
```bash
cd packages/chat && npm install --legacy-peer-deps
```
**Result**: ✅ Chat package got its dependencies, ❌ staging build still failed

### **2. Add to Staging Package.json**
**File**: `jupyterlab/staging/package.json`
```json
{
  "resolutions": {
    "@jupyterlab/chat": "~4.1.0",
    "@jupyterlab/chat-extension": "~4.1.0"
  },
  "dependencies": {
    "@jupyterlab/chat-extension": "~4.1.0"
  }
}
```
**Result**: ❌ Still tries to fetch from npm registry

### **3. Add to Build Config**
**File**: `/mambaforge/share/jupyter/lab/settings/build_config.json`
```json
{
    "local_extensions": {
        "@jupyterlab/chat": "/path/to/packages/chat",
        "@jupyterlab/chat-extension": "/path/to/packages/chat-extension"
    }
}
```
**Result**: ❌ Doesn't affect staging dependency resolution

### **4. Manual Package Placement**
```bash
cd packages/chat && npm pack
cp jupyterlab-chat-4.1.0.tgz /mambaforge/share/jupyter/lab/extensions/
```
**Result**: ❌ Staging still looks at npm registry, ignores local tarball

### **5. Production Build Flags**
```bash
jupyter lab build --dev-build=False --minimize=False
```
**Result**: ❌ Same 404 error

---

## 📚 **Research Findings**

### **npm Documentation**
> "Packages linked by local path will not have their own dependencies installed when npm install is ran. You must run npm install from inside the local path itself."

### **JupyterLab Build Documentation**
- **Staging build is intentionally isolated** for reproducible builds
- **Local extensions expected to be self-contained** or reference published packages
- **Workspace dependencies not supported** in production builds

### **Common Solutions in the Wild**
1. **Private npm registry** (Verdaccio, GitHub Packages)
2. **Monorepo with proper build tools** (Lerna, Rush)
3. **Single extension approach** (bundle everything together)
4. **Custom build scripts** that handle workspace deps

---

## ✅ **Current Working Solution**

### **Use Development Flags**
```bash
jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890
```

**Why this works**:
- ✅ **Bypasses staging build** - uses extensions directly from source
- ✅ **Preserves workspace relationships** - chat-extension can import from chat
- ✅ **Real-time updates** - changes reflect immediately
- ✅ **Full functionality** - all features work perfectly

**Flags explained**:
- `--dev-mode`: Uses development build instead of production
- `--extensions-in-dev-mode`: Loads extensions from source directories
- `--ServerApp.log_level=DEBUG`: Verbose logging for debugging
- `--port=8890`: Custom port (optional)

---

## 🚀 **Future Production Solutions**

### **Option 1: Private npm Registry** (Recommended)
```bash
# Set up Verdaccio or similar
npm install -g verdaccio
verdaccio

# Publish packages
cd packages/chat && npm publish --registry http://localhost:4873
cd packages/chat-extension && npm publish --registry http://localhost:4873

# Configure .npmrc
echo "registry=http://localhost:4873" > .npmrc
```

### **Option 2: Single Extension Approach**
- Move all chat functionality into `chat-extension`
- Remove separate `chat` package
- Self-contained extension with no external dependencies

### **Option 3: Custom Build Process**
- Create build script that:
  1. Packs both packages to staging
  2. Modifies dependencies to use file: references
  3. Runs JupyterLab build

### **Option 4: Monorepo Tools**
- Use Lerna, Rush, or similar tools
- Proper workspace management
- Automated publishing workflows

---

## 🛠️ **Development Workflow**

### **Current Commands**
```bash
# Start development environment
conda activate jupyterlab-ext
jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890

# Make changes to packages/chat or packages/chat-extension
# Changes are automatically available (no rebuild needed)

# For TypeScript changes, run in separate terminal:
cd packages/chat && npm run watch
cd packages/chat-extension && npm run watch
```

### **Testing Production Build**
```bash
# This will fail until we implement one of the solutions above
jupyter lab build

# Check for errors in logs
ls -la /var/folders/*/T/jupyterlab-debug-*.log
```

---

## 📝 **Key Takeaways**

1. **Our architecture is correct** - follows JupyterLab conventions
2. **Dev flags are the intended solution** for development with local dependencies
3. **Production builds require published packages** or alternative approaches
4. **This is a known limitation**, not a bug we can easily fix
5. **Many JupyterLab extensions face this same issue**

---

## 🔄 **When to Revisit**

**Revisit this issue when**:
- Ready to deploy to production
- Need to distribute the extension to others
- Want to optimize build performance
- JupyterLab updates their build system

**Don't revisit if**:
- Still actively developing features
- Dev-mode workflow is sufficient
- Not ready for production deployment

---

## 📞 **Resources**

- [JupyterLab Extension Tutorial](https://jupyterlab.readthedocs.io/en/latest/extension/extension_tutorial.html)
- [JupyterLab Advanced Usage](https://jupyterlab.readthedocs.io/en/latest/user/directories.html)
- [npm Workspaces Documentation](https://docs.npmjs.com/cli/v7/using-npm/workspaces)
- [Verdaccio Private Registry](https://verdaccio.org/)

---

**Last Updated**: September 2025
**Status**: Development working with dev flags, production build unresolved
