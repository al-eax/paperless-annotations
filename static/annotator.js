import EmbedPDF from './embedpdf.js';
import Api from './api.js'
import { paperlessIcon } from './icons.js';
/**
 * Handles UI customizations for the EmbedPDF viewer.
 */
class UiPatch {
  /**
   * @param {number} docId - Document identifier
   * @param {string} authorName - Current user's name
   * @param {string} paperlessUrl - Base URL for Paperless-ngx instance
   * @param {Object} viewer - EmbedPDF viewer instance
   * @param {Object} api - API client instance
   */
  constructor(docId, authorName, paperlessUrl, viewer, api) {
    this.docId = docId;
    this.authorName = authorName;
    this.paperlessUrl = paperlessUrl;
    this.viewer = viewer;
    this.api = api;
  }

  /**
   * Applies all UI customizations to the viewer.
   */
  patchUi() {
    // this._addLogoutButton();
    this._syncThemeWithNavbar();
    this._patchDocMenuItems();
    this._addPaperlessMenuItem();
    console.log("Patching UI...");
    this._removeStampFromAnnotateToolbar();
  }

  /**
   * Adds a custom "Open in Paperless" menu item to the document menu.
   * @private
   */
  async _addPaperlessMenuItem() {
    const { registry, ui } = await this._getRegistryAndUi();
    const commands = registry.getPlugin('commands').provides();

    this.viewer.registerIcon('paperless-icon', paperlessIcon);
    const cmdId = "plannotations.btn-open-paperless";
    commands.registerCommand({
      id: cmdId,
      label: 'Open in Paperless',
      icon: 'paperless-icon',
      action: () => {
        window.open(`${this.paperlessUrl}/documents/${this.docId}`, '_blank');
      }
    });

    const menu = this._getMenu(ui, 'document-menu');
    if (!menu) return;

    const updatedItems = [
      ...menu.items,
      { type: 'divider', id: 'menu-divider' },
      { type: 'command', id: 'menu-item-paperless', commandId: cmdId }
    ];

    ui.mergeSchema({
      menus: { 'document-menu': { ...menu, items: updatedItems } }
    });
  }

  /**
   * Removes unwanted items from the document menu (open/close commands).
   * @private
   */
  async _patchDocMenuItems() {
    const { ui } = await this._getRegistryAndUi();
    const menu = this._getMenu(ui, 'document-menu');
    if (!menu) return;

    menu.items = menu.items.filter(
      item => !['document:open', 'document:close', 'divider-10'].some(id => item.id.includes(id))
    );

    ui.mergeSchema({
      menus: { 'document-menu': { ...menu } }
    });
  }


  /**
   * Syncs the PDF viewer theme with the navbar theme toggle.
   * Listens for themechange events and sets initial theme from localStorage/data-theme.
   * @private
   */
  _syncThemeWithNavbar() {
    // Set initial theme from current page theme
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    this.viewer.setTheme(currentTheme);

    // Listen for theme changes from navbar toggle
    window.addEventListener('themechange', (event) => {
      this.viewer.setTheme(event.detail.theme);
    });
  }

  /**
   * Removes the stamp tool from the annotation toolbar.
   * @private
   */
  async _removeStampFromAnnotateToolbar() {
    const { ui } = await this._getRegistryAndUi();
    const toolbar = this._getToolbar(ui, 'annotation-toolbar');
    if (!toolbar) return;

    toolbar.items = toolbar.items.map(item => {
      if (item.id === 'annotation-tools' && item.items) {
        item.items = item.items.filter(subitem => subitem.id !== 'add-stamp');
        console.log(item.items);
      }
      return item;
    });

    ui.mergeSchema({
      toolbars: { 'annotation-toolbar': { ...toolbar } }
    });
  }

  /**
   * Helper to get registry and UI plugin.
   * @private
   * @returns {Promise<{registry: Object, ui: Object}>}
   */
  async _getRegistryAndUi() {
    const registry = await this.viewer.registry;
    const ui = registry.getPlugin('ui').provides();
    return { registry, ui };
  }

  /**
   * Helper to get a menu from the schema with error handling.
   * @private
   * @param {Object} ui - UI plugin instance
   * @param {string} menuId - Menu identifier
   * @returns {Object|null} Menu object or null if not found
   */
  _getMenu(ui, menuId) {
    const menu = ui.getSchema().menus[menuId];
    if (!menu) {
      console.warn(`Menu '${menuId}' not found`);
      return null;
    }
    return menu;
  }

  /**
   * Helper to get a toolbar from the schema with error handling.
   * @private
   * @param {Object} ui - UI plugin instance
   * @param {string} toolbarId - Toolbar identifier
   * @returns {Object|null} Toolbar object or null if not found
   */
  _getToolbar(ui, toolbarId) {
    const toolbar = ui.getSchema().toolbars[toolbarId];
    if (!toolbar) {
      console.warn(`Toolbar '${toolbarId}' not found`);
      return null;
    }
    return toolbar;
  }
}


/**
 * Main controller for PDF annotation functionality.
 * Manages the EmbedPDF viewer, API communication, and annotation synchronization.
 */
export class PaperlessAnnotationsViewer {
  /**
   * @param {number} docId - Document identifier
   * @param {string} authorName - Current user's name
   * @param {string} paperlessUrl - Base URL for Paperless-ngx instance
   */
  constructor(docId, authorName, paperlessUrl, jumpToAnno = null) {
    this.docId = docId;
    this.authorName = authorName;
    this.paperlessUrl = paperlessUrl;
    this.api = Api(docId, window.showError);
    this.viewer = null;
    this.registry = null;
    this.jumpToAnno = jumpToAnno;
    this.createViewer();
  }

  /**
   * Initializes the EmbedPDF viewer and sets up event handlers.
   * @private
   */
  async createViewer() {
    this.viewer = await EmbedPDF.init({
      type: 'container',
      target: document.getElementById('pdf-viewer'),
      src: `/api/documents/${this.docId}/download`,
      disabledCategories: ['redaction']
    });

    this.registry = await this.viewer.registry;
    this._setAnnotationAuthor();
    this._attachAnnotationEventHandlers();
    this._setupDocumentLoadHandler();

    // Apply UI customizations after viewer is ready
    const uiPatch = new UiPatch(this.docId, this.authorName, this.paperlessUrl, this.viewer, this.api);
    uiPatch.patchUi();
  }

  /**
   * Sets up handler to load annotations when document opens.
   * @private
   */
  _setupDocumentLoadHandler() {
    const docManager = this.registry.getPlugin('document-manager').provides();
    docManager.onDocumentOpened(() => {
      this._loadAnnotationsFromServer();
    });
  }

  /**
   * Loads annotations from the server and creates them in the viewer.
   * @private
   */
  async _loadAnnotationsFromServer() {
    try {
      const annos = await this.api.getAnnosForDocument(this.docId);
      const annoApi = await this._getAnnotationApi();
      const eid = ""; // document id

      annos.forEach(anno => {
        anno._comesFromRemote = true;
        anno.created = new Date(anno.created);
        annoApi.createAnnotation(anno.pageIndex, anno, void 0, eid);
      });
    } catch (error) {
      console.error("Failed to load annotations:", error);
      window.showMessage(`Failed to load annotations: ${error.message || error}`);
    }
  }

  /**
   * Sets the annotation author for newly created annotations.
   * @private
   */
  _setAnnotationAuthor() {
    const plugin = this.registry.getPlugin('annotation');
    plugin.config.annotationAuthor = this.authorName;
  }

  /**
   * Attaches event handlers for annotation create/update/delete events.
   * @private
   */
  async _attachAnnotationEventHandlers() {
    const annoApi = await this._getAnnotationApi();

    annoApi.onAnnotationEvent((event) => {
      if (event.committed) {
        return event; // Skip uncommitted events
      }

      switch (event.type) {
        case 'create':
          this._handleAnnotationCreated(event.annotation);
          break;
        case 'update':
          this._handleAnnotationUpdated(event);
          break;
        case 'delete':
          this._handleAnnotationDeleted(event.annotation);
          break;
      }

      return event;
    });
  }

  /**
   * Handles annotation creation events.
   * @private
   * @param {Object} anno - Annotation object
   */
  _handleAnnotationCreated(anno) {
    if (anno._comesFromRemote) return;

    this.api.createAnno(anno)
      .then(async (createdAnno) => {
        anno.db_id = createdAnno.db_id;
        const annoApi = await this._getAnnotationApi();
        annoApi.updateAnnotation(anno.pageIndex, anno.id, { db_id: createdAnno.db_id });
      })
      .catch(error => {
        window.showMessage(`Failed to create annotation: ${error.message || error}`);
      });
  }

  /**
   * Handles annotation update events.
   * @private
   * @param {Object} event - Update event with annotation and patch
   */
  _handleAnnotationUpdated(event) {
    // Skip updates that only contain db_id and author to avoid recursion
    const patchKeys = Object.keys(event.patch);
    if (patchKeys.length === 2 &&
      patchKeys.includes('db_id') &&
      patchKeys.includes('author')) {
      return;
    }

    // Normalize values (convert Dates to ISO, round numbers, sort object keys)
    // and compare JSON strings. Only compare the keys present in the patch.
    const normalize = (v) => {
      // if (v === null || v === undefined) return v;
      // if (v instanceof Date) return v.toISOString();
      // if (typeof v === 'number') return Math.round(v * 1e6) / 1e6; // round to 6 decimals
      // if (Array.isArray(v)) return v.map(normalize);
      // if (typeof v === 'object') {
      //   const out = {};
      //   Object.keys(v).sort().forEach((k) => {
      //     out[k] = normalize(v[k]);
      //   });
      //   return out;
      // }
      return v;
    };

    let hasChanges = false;
    for (const key of patchKeys) {
      const a = normalize(event.annotation[key]);
      const b = normalize(event.patch[key]);
      if (JSON.stringify(a) !== JSON.stringify(b)) {
        hasChanges = true;
        break;
      }
    }
    if (!hasChanges) return;
    console.log("Updating annotation:", event.annotation, event.patch);
    // Apply patch to annotation
    Object.assign(event.annotation, event.patch);


    this.api.updateAnno(event.annotation)
      .then(async (updatedAnno) => {
        const annoApi = await this._getAnnotationApi();
        annoApi.updateAnnotation(updatedAnno.pageIndex, event.annotation.id, { db_id: updatedAnno.db_id });
      })
      .catch(error => {
        window.showMessage(`Failed to update annotation: ${error.message || error}`);
      });
  }

  /**
   * Handles annotation deletion events.
   * @private
   * @param {Object} anno - Annotation object
   */
  _handleAnnotationDeleted(anno) {
    if (!anno._comesFromRemote) {
      // annotation is part of the document and wasnt created by the user
      return;
    }
    this.api.deleteAnno(anno)
      .catch(error => {
        window.showMessage(`Failed to delete annotation: ${error.message || error}`);
      });
  }


  /**
   * Gets the annotation API from the registry.
   * @private
   * @returns {Promise<Object>} Annotation API instance
   */
  async _getAnnotationApi() {
    const plugin = this.registry.getPlugin('annotation');
    return await plugin.provides();
  }
}

