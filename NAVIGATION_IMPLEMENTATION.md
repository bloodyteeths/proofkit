# Navigation Active State Implementation

This document explains the Jinja2 macro implementation for navigation active state detection in ProofKit.

## Overview

The navigation system now includes sophisticated active state detection that works with:
- Main navigation links (Home, Examples, Docs, Trust)
- Industry-specific routes (Powder-Coat, HACCP, Autoclave, etc.)
- Dropdown toggles that show active state when any child is active

## Files Created/Modified

### 1. Navigation Macros
**File**: `/web/templates/macros/navigation.html`

Contains Jinja2 macros for:
- `is_active_nav()` - Determines if a navigation item should be active
- `nav_class()` - Generates CSS classes with active state
- `nav_link()` - Complete navigation link with automatic active detection
- `is_industry_active()` - Checks if any industry in a list is active
- `dropdown_toggle_class()` - CSS classes for dropdown toggles
- `is_home_page()` - Detects home page without industry parameter
- `get_current_industry()` - Returns current industry parameter
- `debug_nav_info()` - Debug helper for development

### 2. Navigation Component
**File**: `/web/templates/nav.html`

Updated to use the new macros:
- Industry dropdown toggle shows active state when any industry is selected
- All dropdown items use macro-based active detection
- Secondary navigation links use macro-based active detection
- Added CSS styling for active dropdown toggle state

### 3. Template Integration
**Files**: `/web/templates/base.html`, `/web/templates/layout.html`

Both templates now include the navigation component:
- Removed old hardcoded navigation from `base.html`
- Updated `layout.html` to use the new navigation component
- Ensures consistent navigation across all pages

### 4. Demo Page
**File**: `/web/templates/nav_demo.html`

Created demonstration page showing:
- Current request information
- Active state visualization
- Test links for different routes
- Debug table showing macro results

**Route**: `/nav_demo` - Added to `app.py` for testing

## Usage Examples

### Basic Navigation Link
```jinja2
{% from 'macros/navigation.html' import nav_class %}

<a href="/examples" class="{{ nav_class(request, '/examples', base_classes='nav-link') }}">
    Examples
</a>
```

### Industry-Specific Link
```jinja2
<a href="/?industry=powder-coat" 
   class="{{ nav_class(request, '/', 'powder-coat', 'nav-dropdown-item') }}">
    🎨 Powder-Coat
</a>
```

### Dropdown Toggle with Active Detection
```jinja2
{% from 'macros/navigation.html' import dropdown_toggle_class %}

<button class="{{ dropdown_toggle_class(request, ['powder-coat', 'haccp'], 'nav-dropdown-toggle') }}">
    Industries
</button>
```

### Conditional Content Based on Active State
```jinja2
{% from 'macros/navigation.html' import is_active_nav, is_home_page %}

{% if is_home_page(request) %}
    <p>Welcome to ProofKit!</p>
{% endif %}

{% if is_active_nav(request, '/trust') %}
    <p>You're viewing our trust and security information.</p>
{% endif %}
```

## Route Detection Logic

### Home Page Routes
- `/` with no industry parameter → Home page
- `/?industry=powder-coat` → Powder-Coat industry page
- `/?industry=haccp` → HACCP industry page
- etc.

### Standard Routes
- `/examples` → Examples page
- `/docs` → API Documentation (FastAPI auto-generated)
- `/trust` → Trust & Security page
- `/verify/{bundle_id}` → Verification page

### Active State Rules

1. **Exact Match (default)**: Path must match exactly
2. **Industry Match**: Home path (`/`) + matching industry parameter
3. **Prefix Match**: For parent pages with children (use `exact_match=False`)

## CSS Classes

### Base Classes
- `nav-link` - Standard navigation link
- `nav-dropdown-item` - Dropdown menu item
- `nav-dropdown-toggle` - Dropdown toggle button

### Active Classes
- `active` - Default active state class
- Can be customized with `active_class` parameter

### CSS Styling
```css
.nav-link.active,
.nav-dropdown-item.active,
.nav-dropdown-toggle.active {
    background: rgba(255, 255, 255, 0.2) !important;
    color: white !important;
}

.nav-dropdown-item.active {
    background: #667eea !important;
    color: white !important;
}

.nav-dropdown-toggle.active {
    background: rgba(255, 255, 255, 0.2) !important;
    border-color: rgba(255, 255, 255, 0.4) !important;
}
```

## Testing

### Manual Testing
Visit `/nav_demo` to see the navigation in action:
- Test different routes
- Verify active states
- Check industry parameter detection
- Debug macro results

### Test Scenarios
1. Home page (no industry) - Only home should be active
2. Industry pages (e.g., `/?industry=powder-coat`) - Industry dropdown toggle and specific item should be active
3. Examples page (`/examples`) - Examples link should be active
4. Trust page (`/trust`) - Trust link should be active
5. Docs page (`/docs`) - Docs link should be active

## Integration Notes

### FastAPI Request Object
The macros expect the standard FastAPI `Request` object with:
- `request.url.path` - Current URL path
- `request.url.query_params` - Query parameters dict-like object
- `request.url.query` - Raw query string

### Template Inheritance
All templates extending `base.html` or `layout.html` automatically get the new navigation:
- `index.html` (Home page)
- `examples.html` (Examples page)
- `trust.html` (Trust page)
- `verify.html` (Verification page)
- `error.html` (Error page)
- `result.html` (Results page)
- All industry-specific templates

### Backwards Compatibility
The implementation maintains full backwards compatibility:
- Existing templates continue to work
- No changes required to route handlers
- CSS classes remain consistent

## Performance Considerations

- Macros are compiled once and cached by Jinja2
- Active state detection uses simple string comparisons
- No database queries or complex logic
- Minimal overhead per request

## Future Enhancements

Potential improvements that could be added:

1. **Breadcrumb Navigation**: Use similar macro logic for breadcrumbs
2. **Multi-level Dropdowns**: Extend for nested menu structures  
3. **Dynamic Menu Loading**: Generate navigation from configuration
4. **Access Control**: Integrate with user permissions system
5. **Analytics Integration**: Track navigation usage patterns

## Troubleshooting

### Common Issues

1. **Active state not working**: Ensure `request` object is passed to template
2. **Industry detection failing**: Check query parameter format (`?industry=value`)
3. **CSS not applying**: Verify CSS classes are loaded and !important rules
4. **Dropdown not highlighting**: Ensure all industry values are in the list

### Debug Mode
Use the `debug_nav_info()` macro to display current request information:
```jinja2
{% from 'macros/navigation.html' import debug_nav_info %}
{{ debug_nav_info(request) }}
```

## Maintenance

### Adding New Routes
1. Add route handler to `app.py`
2. Add navigation link to `nav.html` using macros
3. Test active state detection
4. Update CSS if needed

### Adding New Industries
1. Add link to industry dropdown in `nav.html`
2. Include industry in `dropdown_toggle_class()` list
3. Create industry-specific template if needed
4. Add preset configuration

This implementation provides a robust, maintainable, and extensible navigation system that automatically handles active state detection across all ProofKit pages.