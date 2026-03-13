#!/usr/bin/env python3
"""
Calendar Sync Menu Bar App

A macOS menu bar app that syncs personal calendar events to work calendar.
Shows calendar events, sync status, and allows manual sync.
Uses rumps for reliable menu bar integration and EventKit for all calendar operations.
"""

import sys
import os
import logging
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# Fix SSL certificates for bundled app - must be done BEFORE importing google libs
def _fix_ssl_certificates():
    """Set up SSL certificates for bundled macOS app.
    
    When running as a py2app bundle, certifi may cache a temp path that no longer exists.
    This ensures SSL_CERT_FILE and SSL_CERT_DIR point to valid certificate files.
    """
    # Check if we're running in a bundled app
    if getattr(sys, 'frozen', False):
        # Running in a py2app bundle
        resource_path = os.environ.get('RESOURCEPATH', '')
        cert_file = os.path.join(resource_path, 'openssl.ca', 'cert.pem')
        cert_dir = os.path.join(resource_path, 'openssl.ca', 'certs')
        
        if os.path.exists(cert_file):
            os.environ['SSL_CERT_FILE'] = cert_file
            os.environ['SSL_CERT_DIR'] = cert_dir
            os.environ['REQUESTS_CA_BUNDLE'] = cert_file
            os.environ['CURL_CA_BUNDLE'] = cert_file
            
            # Also patch certifi if it's already imported
            try:
                import certifi
                certifi.where = lambda: cert_file
            except ImportError:
                pass
            
            return True
    return False

_fix_ssl_certificates()

# Use standard macOS Application Support directory
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "CalendarSync"
APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = APP_SUPPORT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'menubar_debug.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logger.info("=" * 60)
logger.info("Calendar Sync menubar starting...")
logger.info(f"Python: {sys.executable}")
logger.info(f"Working dir: {Path.cwd()}")

try:
    import rumps
    logger.info("rumps imported successfully")
except ImportError as e:
    logger.error(f"Failed to import rumps: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)

try:
    # Import sync function directly to run in-process (shares calendar permissions)
    # Use the EventKit-only version (no Google API dependencies)
    from calendar_sync_eventkit import sync_calendars
    logger.info("calendar_sync_eventkit imported successfully")
except ImportError as e:
    logger.error(f"Failed to import calendar_sync_eventkit: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)

try:
    # For calendar change notifications and hiding dock icon
    from Foundation import NSNotificationCenter, NSBundle
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
    import EventKit
    logger.info("macOS frameworks imported successfully")
except ImportError as e:
    logger.error(f"Failed to import macOS frameworks: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)

# Hide dock icon before anything else
try:
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    logger.info("Dock icon hidden")
except Exception as e:
    logger.error(f"Failed to hide dock icon: {e}")

# Import sync mapping functions
from calendar_sync_eventkit import load_personal_block_mapping, PERSONAL_BLOCK_MAPPING_FILE

# Configuration
DEBOUNCE_SECONDS = 5
MIN_SYNC_INTERVAL = 30
PERIODIC_SYNC_INTERVAL = 1800  # 30 minutes fallback sync
SYNC_SCRIPT = Path(__file__).parent / "calendar_sync.py"

# Icon paths - handle both development and bundled app
# In py2app bundle, __file__ is in Contents/Resources, and icons are in Contents/Resources/icons
ICONS_DIR = Path(__file__).parent / "icons"

# Verify icons exist, fall back to None if not found
def _get_icon_path(name):
    path = ICONS_DIR / name
    if path.exists():
        return str(path)
    logger.warning(f"Icon not found: {path}")
    return None

ICON_IDLE = _get_icon_path("calendar_idle.png")  # Idle state
ICON_SYNCED = _get_icon_path("sync_success.png")  # Successfully synced
ICON_MANUAL_SYNC = _get_icon_path("manualsync.png")
ICON_SCHEDULED_SYNC = _get_icon_path("schedule_sync.png")
ICON_SUCCESS = _get_icon_path("sync_success.png")  # Sync success
ICON_WARNING = _get_icon_path("warning.png")
ICON_FAILED = _get_icon_path("sync_failed.png")

logger.info(f"Icons directory: {ICONS_DIR}, exists: {ICONS_DIR.exists()}")


class CalendarSyncApp(rumps.App):
    def __init__(self):
        super(CalendarSyncApp, self).__init__(
            "Calendar Sync",
            icon=ICON_IDLE,
            title=None,
            template=True,  # Make icon render as white/dark mode adaptive
            quit_button=None  # We'll add our own
        )
        
        logger.info("CalendarSyncApp.__init__ starting...")
        
        self.last_sync_time = None
        self.pending_sync = False
        self.sync_timer = None
        self.is_syncing = False
        
        # Create EventKit store for calendar notifications and sync
        logger.info("Creating EventKit store...")
        self.store = EventKit.EKEventStore.alloc().init()
        
        # Request calendar access at startup
        logger.info("Requesting calendar access...")
        self._request_calendar_access()
        
        # Cache calendar colors
        self.calendar_colors = {}
        self._cache_calendar_colors()
        
        # Build menu
        logger.info("Building menu...")
        self.status_item = rumps.MenuItem("Status: Idle")
        self.status_item.set_callback(None)
        self.last_sync_item = rumps.MenuItem("Last sync: Never")
        self.last_sync_item.set_callback(None)
        
        # Events will be added directly to menu, track them for updates
        self.event_items = []
        
        # Keep reference to settings controller to prevent garbage collection
        self.settings_controller = None
        
        # Use string keys for menu items we need to reference
        self.menu = [
            # Events will be inserted at top dynamically
            rumps.MenuItem("Sync Now", callback=self.sync_now),
            self.status_item,
            self.last_sync_item,
            None,  # Separator
            rumps.MenuItem("Settings...", callback=self.open_settings_window),
            rumps.MenuItem("View Logs", callback=self.view_logs),
            None,  # Separator
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]
        
        # Refresh events on startup (after menu is built)
        # Delay slightly to ensure menu is initialized
        threading.Timer(0.5, self._refresh_events_menu).start()
        
        # Register for calendar change notifications
        logger.info("Setting up calendar observer...")
        self._setup_calendar_observer()
        
        # Start periodic sync timer
        logger.info("Starting periodic sync timer...")
        self._start_periodic_sync()
        
        # Run initial sync after a short delay
        logger.info("Scheduling initial sync...")
        threading.Timer(2.0, self._do_sync).start()
        
        # Set icon with proper sizing after app is initialized
        self._set_icon(ICON_IDLE)
        
        logger.info("Calendar Sync running in menu bar...")
    
    def _request_calendar_access(self):
        """Request calendar access at startup."""
        import platform
        from Foundation import NSRunLoop, NSDate as FoundationNSDate
        
        result = {'granted': None}
        
        def completion_handler(granted, error):
            result['granted'] = granted
            if granted:
                logger.info("✅ Calendar access granted")
            else:
                logger.error(f"❌ Calendar access denied: {error}")
        
        macos_version = tuple(map(int, platform.mac_ver()[0].split('.')))
        logger.info(f"macOS version: {macos_version}")
        
        if macos_version >= (14, 0):
            try:
                logger.info("Using macOS 14+ full access API...")
                self.store.requestFullAccessToEventsWithCompletion_(completion_handler)
            except AttributeError:
                logger.info("Falling back to legacy API...")
                self.store.requestAccessToEntityType_completion_(
                    EventKit.EKEntityTypeEvent, completion_handler
                )
        else:
            logger.info("Using legacy API...")
            self.store.requestAccessToEntityType_completion_(
                EventKit.EKEntityTypeEvent, completion_handler
            )
        
        # Wait briefly for the response
        timeout = 5
        import time
        start = time.time()
        while result['granted'] is None and (time.time() - start) < timeout:
            NSRunLoop.currentRunLoop().runUntilDate_(
                FoundationNSDate.dateWithTimeIntervalSinceNow_(0.1)
            )
        
        self.has_calendar_access = result['granted'] or False
    
    def _set_template_icon(self):
        """Set the menu bar icon as a template so it renders white/dark mode adaptive."""
        try:
            from AppKit import NSImage
            # Get the status bar button and set template
            status_item = rumps.rumps._clicked_ns_object_weak_ref()
            if status_item:
                button = status_item.button()
                if button and button.image():
                    button.image().setTemplate_(True)
        except Exception as e:
            logger.debug(f"Could not set template icon: {e}")
    
    def _set_icon(self, icon_path):
        """Set the menu bar icon with proper sizing and template mode."""
        try:
            from AppKit import NSImage, NSSize
            
            if not icon_path:
                return
                
            # Load the image
            image = NSImage.alloc().initWithContentsOfFile_(icon_path)
            if image:
                # Get original size
                orig_size = image.size()
                
                # Menu bar icons should be ~18-22 points tall
                # Preserve aspect ratio
                target_height = 18.0
                aspect_ratio = orig_size.width / orig_size.height if orig_size.height > 0 else 1.0
                target_width = target_height * aspect_ratio
                
                # Set the size
                image.setSize_(NSSize(target_width, target_height))
                
                # Make it a template image for dark/light mode
                image.setTemplate_(True)
                
                # Set directly on the status item button
                if hasattr(self, '_nsapp') and self._nsapp:
                    si = self._nsapp.nsstatusitem
                    if si and si.button():
                        si.button().setImage_(image)
                        return
                
            # Fallback to rumps default
            self.icon = icon_path
        except Exception as e:
            logger.debug(f"Could not set icon with sizing: {e}")
            self.icon = icon_path
    
    def _cache_calendar_colors(self):
        """Cache calendar icon paths for known calendars."""
        # Map calendar names to their icon files
        self.calendar_icons = {
            'Calendar': _get_icon_path("workcal.png"),
            'Personal Cal': _get_icon_path("personalcal.png"),
            'Release Calendar': _get_icon_path("releasecal.png"),
        }
        logger.info(f"Cached icons for {len(self.calendar_icons)} calendars")
    
    def _refresh_events_menu(self):
        """Refresh events directly in the main menu with calendar icons."""
        try:
            from Foundation import NSDate as FoundationNSDate
            from AppKit import NSMenuItem
            
            # Remove old event items from menu using NSMenu directly
            ns_menu = self.menu._menu
            for item in self.event_items:
                try:
                    if isinstance(item, tuple) and item[0] == 'separator':
                        # Remove native separator
                        ns_menu.removeItem_(item[1])
                    elif hasattr(item, '_menuitem'):
                        # Remove rumps MenuItem
                        ns_menu.removeItem_(item._menuitem)
                except Exception as e:
                    logger.debug(f"Could not remove item: {e}")
            self.event_items = []
            
            # Get events from start of today to 3 days from now
            now = datetime.now()
            today = now.date()
            tomorrow = today + timedelta(days=1)
            day_after = today + timedelta(days=2)
            
            # Start from beginning of today
            start_of_today = datetime.combine(today, datetime.min.time())
            end = now + timedelta(days=3)
            
            ns_start = FoundationNSDate.dateWithTimeIntervalSince1970_(start_of_today.timestamp())
            ns_end = FoundationNSDate.dateWithTimeIntervalSince1970_(end.timestamp())
            
            # Get calendars to display from preferences, with fallback defaults
            from settings_window import get_display_calendar_names
            display_calendar_names = get_display_calendar_names()
            if not display_calendar_names:
                display_calendar_names = ['Calendar', 'Personal Cal', 'Release Calendar']
            
            all_calendars = self.store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
            calendars = [cal for cal in all_calendars if cal.title() in display_calendar_names]
            
            if not calendars:
                logger.info("No matching calendars found")
                return
            
            # Fetch events from filtered calendars only
            predicate = self.store.predicateForEventsWithStartDate_endDate_calendars_(
                ns_start, ns_end, calendars
            )
            events = self.store.eventsMatchingPredicate_(predicate)
            
            # Sort events by start time and filter out cancelled
            sorted_events = []
            if events:
                for event in events:
                    # Skip cancelled events (status 3)
                    if event.status() == 3:
                        continue
                    sorted_events.append(event)
                
                sorted_events.sort(key=lambda e: e.startDate().timeIntervalSince1970())
            
            # Group events by day
            events_by_day = {today: [], tomorrow: [], day_after: []}
            
            for event in sorted_events:
                start_ts = event.startDate().timeIntervalSince1970()
                start_dt = datetime.fromtimestamp(start_ts)
                event_day = start_dt.date()
                
                if event_day in events_by_day:
                    events_by_day[event_day].append((event, start_dt))
            
            # Build event items list
            event_menu_items = []
            max_events_per_day = 5
            
            # Process each day in order
            for day_index, (day, day_events) in enumerate([(today, events_by_day[today]), 
                                                            (tomorrow, events_by_day[tomorrow]),
                                                            (day_after, events_by_day[day_after])]):
                # Add separator before each day except the first
                if day_index > 0 and event_menu_items:
                    # Use native NSMenuItem separator
                    from AppKit import NSMenuItem
                    sep_item = NSMenuItem.separatorItem()
                    event_menu_items.append(('separator', sep_item))
                
                # Determine day label
                if day == today:
                    day_label = f"Today, {day.strftime('%b %d')}"
                elif day == tomorrow:
                    day_label = f"Tomorrow, {day.strftime('%b %d')}"
                else:
                    day_label = day.strftime("%A, %b %d")
                
                # Always show Today header, skip other days if no events
                if day != today and not day_events:
                    continue
                
                # Add day header with bold text
                header = rumps.MenuItem(day_label, callback=lambda _: None)
                # Make header bold using NSAttributedString
                try:
                    from AppKit import NSAttributedString, NSFont, NSFontAttributeName
                    bold_font = NSFont.boldSystemFontOfSize_(13)
                    attrs = {NSFontAttributeName: bold_font}
                    attributed_title = NSAttributedString.alloc().initWithString_attributes_(day_label, attrs)
                    header._menuitem.setAttributedTitle_(attributed_title)
                except Exception as e:
                    logger.debug(f"Could not set bold header: {e}")
                event_menu_items.append(header)
                
                # Add events for this day
                if not day_events:
                    no_events = rumps.MenuItem("   No events", callback=lambda _: None)
                    event_menu_items.append(no_events)
                else:
                    # No limit for today/tomorrow, limit for other days
                    if day == today or day == tomorrow:
                        events_to_show = day_events
                    else:
                        events_to_show = day_events[:max_events_per_day]
                    
                    for i, (event, start_dt) in enumerate(events_to_show):
                        # Get event details
                        title = event.title() or "(No title)"
                        cal = event.calendar()
                        cal_name = cal.title() if cal else "Unknown"
                        event_id = event.eventIdentifier()
                        
                        # Check if all-day event
                        if event.isAllDay():
                            time_str = "All day"
                        else:
                            time_str = start_dt.strftime("%-I:%M %p")
                        
                        # Check if event is in the past (end time has passed)
                        end_date = event.endDate()
                        if end_date:
                            end_dt = datetime.fromtimestamp(end_date.timeIntervalSince1970())
                            is_past = end_dt < datetime.now()
                        else:
                            is_past = start_dt < datetime.now()
                        
                        # Create menu item with icon
                        # Past events and all-day events are greyed out (no callback), future timed events are clickable
                        menu_title = f" {time_str} • {title}"
                        if event.isAllDay() or is_past:
                            event_item = rumps.MenuItem(menu_title, callback=None)
                        else:
                            event_item = rumps.MenuItem(menu_title, callback=lambda _: None)
                        
                        # Set the calendar icon for this event
                        icon_path = self.calendar_icons.get(cal_name)
                        
                        if icon_path:
                            event_item.icon = icon_path
                        
                        event_menu_items.append(event_item)
                    
                    # Show if there are more events (only for days with limits)
                    if day != today and day != tomorrow and len(day_events) > max_events_per_day:
                        more = rumps.MenuItem(f"   +{len(day_events) - max_events_per_day} more...", callback=lambda _: None)
                        event_menu_items.append(more)
            
            # Add final separator after all events
            if event_menu_items:
                from AppKit import NSMenuItem
                final_sep = NSMenuItem.separatorItem()
                event_menu_items.append(('separator', final_sep))
            
            # Insert items at position 0 in reverse order to maintain correct order
            # Use the internal NSMenu directly to insert at specific indices
            ns_menu = self.menu._menu
            
            for item in reversed(event_menu_items):
                # Handle both native separators and rumps MenuItems
                if isinstance(item, tuple) and item[0] == 'separator':
                    ns_menu.insertItem_atIndex_(item[1], 0)
                    self.event_items.append(item)
                else:
                    ns_menu.insertItem_atIndex_(item._menuitem, 0)
                    self.event_items.append(item)
            
            total_events = sum(len(events_by_day[d]) for d in events_by_day)
            logger.info(f"Refreshed events menu with {total_events} events")
            
        except Exception as e:
            logger.error(f"Failed to refresh events menu: {e}")
            logger.error(traceback.format_exc())
    
    def _setup_calendar_observer(self):
        """Set up observer for calendar changes."""
        center = NSNotificationCenter.defaultCenter()
        center.addObserverForName_object_queue_usingBlock_(
            EventKit.EKEventStoreChangedNotification,
            self.store,
            None,
            self._on_calendar_changed
        )
    
    def _on_calendar_changed(self, notification):
        """Called when calendar data changes."""
        print(f"📅 Calendar change detected at {datetime.now().strftime('%H:%M:%S')}")
        self._refresh_events_menu()  # Update events display
        self._schedule_sync()
    
    def _schedule_sync(self):
        """Schedule a sync after debounce period."""
        if self.sync_timer:
            self.sync_timer.cancel()
        
        # Calculate wait time
        if self.last_sync_time:
            elapsed = (datetime.now() - self.last_sync_time).total_seconds()
            if elapsed < MIN_SYNC_INTERVAL:
                wait_time = MIN_SYNC_INTERVAL - elapsed + 1
            else:
                wait_time = DEBOUNCE_SECONDS
        else:
            wait_time = DEBOUNCE_SECONDS
        
        self.pending_sync = True
        self._update_status(f"Syncing in {int(wait_time)}s...")
        self._set_icon(ICON_SCHEDULED_SYNC)
        
        self.sync_timer = threading.Timer(wait_time, self._do_sync)
        self.sync_timer.start()
    
    def _start_periodic_sync(self):
        """Start a periodic sync timer as safety net."""
        self.periodic_timer = threading.Timer(PERIODIC_SYNC_INTERVAL, self._periodic_sync)
        self.periodic_timer.daemon = True
        self.periodic_timer.start()
    
    def _periodic_sync(self):
        """Run periodic sync and reschedule."""
        print(f"⏰ Periodic sync triggered at {datetime.now().strftime('%I:%M %p')}")
        self._do_sync()
        self._start_periodic_sync()
    
    def _update_status(self, status):
        """Update the status display."""
        self.status_item.title = f"Status: {status}"
    
    def _update_last_sync(self):
        """Update the last sync time display."""
        if self.last_sync_time:
            time_str = self.last_sync_time.strftime("%I:%M %p")
            self.last_sync_item.title = f"Last sync: {time_str}"
        else:
            self.last_sync_item.title = "Last sync: Never"
    
    def sync_now(self, _):
        """Manual sync triggered from menu."""
        self._do_sync()
    
    def view_logs(self, _):
        """Open the logs folder in Finder."""
        import subprocess
        log_file = LOG_DIR / "menubar_debug.log"
        if log_file.exists():
            # Open the log file in Console.app or default text editor
            subprocess.run(["open", str(log_file)])
        else:
            # Open the logs folder if no log file yet
            subprocess.run(["open", str(LOG_DIR)])
    
    def open_settings(self, _):
        """Open the app settings folder in Finder."""
        import subprocess
        # Open the Application Support folder where settings are stored
        subprocess.run(["open", str(APP_SUPPORT_DIR)])
    
    def open_settings_window(self, _):
        """Open the settings window with dropdowns."""
        from settings_window import show_settings_window
        
        def on_settings_saved():
            # Refresh menu and trigger sync after settings are saved
            self._refresh_events_menu()
            self._do_sync()
            rumps.notification(
                title="Settings Saved",
                subtitle="",
                message="Calendar settings have been updated."
            )
        
        # Keep reference to prevent garbage collection
        self.settings_controller = show_settings_window(
            store=self.store,
            on_save=on_settings_saved
        )

    def _do_sync(self):
        """Run the calendar sync."""
        if self.is_syncing:
            print("Already syncing, skipping...")
            return
        
        self.is_syncing = True
        self.pending_sync = False
        self._update_status("Syncing...")
        self._set_icon(ICON_MANUAL_SYNC)
        
        # Run sync in background thread
        thread = threading.Thread(target=self._run_sync_thread)
        thread.daemon = True
        thread.start()
    
    def _run_sync_thread(self):
        """Run sync in background thread."""
        try:
            import time
            sync_start = time.time()
            
            # Run sync directly in-process, passing our EventKit store
            # which already has calendar access
            result = sync_calendars(event_store=self.store)
            
            success = result.get('success', False)
            created = result.get('created', 0)
            updated = result.get('updated', 0)
            deleted = result.get('deleted', 0)
            unchanged = result.get('unchanged', 0)
            
            # Log output for debugging (use Application Support directory)
            log_file = LOG_DIR / "sync_output.log"
            with open(log_file, "a") as f:
                f.write(f"\n=== Sync at {datetime.now()} ===\n")
                f.write(f"Result: {result}\n")
            
            # Ensure sync icon shows for at least 0.5 seconds so user sees feedback
            elapsed = time.time() - sync_start
            if elapsed < 0.5:
                time.sleep(0.5 - elapsed)
            
            self._sync_completed(success, created, updated, deleted, unchanged)
            
        except Exception as e:
            print(f"Sync error: {e}")
            self._sync_failed(str(e))
    
    def _sync_completed(self, success, created, updated, deleted, unchanged):
        """Called when sync completes."""
        self.is_syncing = False
        self.last_sync_time = datetime.now()
        self._update_last_sync()
        
        if success:
            changes = created + updated + deleted
            if changes > 0:
                self._update_status(f"✓ {changes} change(s)")
            else:
                self._update_status("✓ Up to date")
            self._set_icon(ICON_SUCCESS)
        else:
            self._update_status("⚠️ Sync had issues")
            self._set_icon(ICON_WARNING)
        
        # Refresh events display after sync
        self._refresh_events_menu()
        
        # Revert to idle icon after 5 seconds
        threading.Timer(5.0, self._revert_to_idle).start()
        
        logger.info(f"Sync completed: +{created} ~{updated} -{deleted}")
    
    def _revert_to_idle(self):
        """Revert icon to idle state if not currently syncing."""
        try:
            if not self.is_syncing:
                self.icon = ICON_IDLE
        except Exception as e:
            logger.debug(f"Could not revert icon: {e}")
    
    def _sync_failed(self, error):
        """Called when sync fails."""
        self.is_syncing = False
        self._update_status("❌ Failed")
        self._set_icon(ICON_FAILED)
        
        # Revert to idle icon after 5 seconds
        threading.Timer(5.0, self._revert_to_idle).start()
        
        logger.error(f"Sync failed: {error}")
    
    def quit_app(self, _):
        """Quit the application."""
        logger.info("Quit requested, shutting down...")
        if self.sync_timer:
            self.sync_timer.cancel()
        if hasattr(self, 'periodic_timer'):
            self.periodic_timer.cancel()
        rumps.quit_application()


if __name__ == "__main__":
    try:
        logger.info("Creating CalendarSyncApp instance...")
        app = CalendarSyncApp()
        logger.info("Starting app.run()...")
        app.run()
    except Exception as e:
        logger.error(f"App crashed: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
