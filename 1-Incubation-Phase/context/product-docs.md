# TaskFlow — Product Documentation

## Table of Contents
1. [Getting Started](#getting-started)
2. [Core Features](#core-features)
3. [Integrations](#integrations)
4. [Account Management](#account-management)
5. [Mobile App](#mobile-app)
6. [Troubleshooting](#troubleshooting)
7. [Frequently Asked Questions](#frequently-asked-questions)

---

## Getting Started

### Creating Your Account
1. Visit **app.taskflow.io/signup**
2. Enter your work email address and choose a password (minimum 8 characters, must include one uppercase letter and one number)
3. Verify your email by clicking the confirmation link (valid for 24 hours)
4. Choose your workspace name (this can be changed later in Settings → Workspace)
5. Select your plan (Free, Pro, or Enterprise) — you can start with Free and upgrade anytime
6. Complete the onboarding wizard: pick your industry, team size, and preferred project views

### Creating Your First Project
1. Click the **"+ New Project"** button in the left sidebar
2. Choose a template (Blank, Software Development, Marketing Campaign, Client Project, Product Launch) or start from scratch
3. Give your project a name and optional description
4. Choose a default view: **Board** (Kanban), **List**, **Calendar**, or **Gantt**
5. Set project visibility: **Public** (all workspace members) or **Private** (invited members only)
6. Click **"Create Project"**

### Inviting Team Members
1. Go to **Settings → Members**
2. Click **"Invite Members"**
3. Enter email addresses (comma-separated for bulk invites, up to 20 at a time)
4. Assign a role: **Admin**, **Member**, or **Guest**
5. Optionally assign them to specific projects
6. Click **"Send Invitations"** — they'll receive an email with a join link (valid for 7 days)

**Role Permissions:**

| Permission | Admin | Member | Guest |
|------------|-------|--------|-------|
| Create projects | Yes | Yes | No |
| Delete projects | Yes | No | No |
| Invite members | Yes | No | No |
| Manage billing | Yes | No | No |
| Create tasks | Yes | Yes | Yes (assigned projects only) |
| View all projects | Yes | Yes | No (assigned only) |
| Access settings | Yes | Limited | No |
| View reports | Yes | Yes | No |
| Use API | Yes | Yes | No |

---

## Core Features

### Task Management

Tasks are the building blocks of every project in TaskFlow.

**Creating a Task:**
1. Open a project and click **"+ Add Task"** (or press **T** as a keyboard shortcut)
2. Enter a task title (required)
3. Add optional details:
   - **Description** — Rich text with markdown support, checklists, and embedded images
   - **Assignee** — One or more team members
   - **Due date** — Single date or date range
   - **Priority** — Urgent, High, Medium, Low (color-coded)
   - **Labels** — Custom color-coded tags (e.g., "Bug", "Frontend", "Client Request")
   - **Estimated time** — For time tracking and workload planning
   - **Subtasks** — Break down work into smaller checkable items
   - **Dependencies** — Link tasks that must be completed first (blocking/blocked by)
   - **Attachments** — Upload files up to 250 MB each

**Task Statuses:**
Default statuses are: To Do → In Progress → In Review → Done
Custom statuses can be created in **Project Settings → Statuses** (Pro and Enterprise plans).

**Bulk Actions:**
Select multiple tasks with Ctrl/Cmd+Click, then:
- Move to another status
- Reassign
- Change priority
- Add/remove labels
- Delete

**Keyboard Shortcuts:**
| Shortcut | Action |
|----------|--------|
| T | New task |
| E | Edit selected task |
| Ctrl/Cmd + Enter | Save task |
| D | Set due date |
| P | Change priority |
| L | Add label |
| / | Search tasks |
| ? | Show all shortcuts |

### Project Boards

TaskFlow offers four views for every project:

**Board View (Kanban):**
- Drag-and-drop cards between status columns
- WIP (Work in Progress) limits available on Pro+ plans
- Swimlanes by assignee, priority, or label
- Card preview shows assignee avatar, due date, label chips, and subtask progress

**List View:**
- Spreadsheet-like view with sortable columns
- Inline editing for all fields
- Group by: status, assignee, priority, due date, or label
- Bulk select and edit

**Calendar View:**
- Tasks displayed by due date on a monthly/weekly calendar
- Drag tasks to reschedule
- Color-coded by project or priority
- iCal feed URL available for syncing to external calendars (Pro+)

**Gantt View (Pro and Enterprise only):**
- Timeline visualization with task bars
- Dependency arrows between linked tasks
- Critical path highlighting
- Drag to adjust dates and durations
- Export to PDF

### Time Tracking

Built-in time tracking helps teams log effort and manage billable hours.

**How to Track Time:**
1. **Timer method:** Open a task, click the **clock icon** to start a timer. Click again to stop. Time is logged automatically.
2. **Manual entry:** Open a task → Time Tracking tab → Click **"+ Add Time Entry"** → Enter date, duration, and optional note.
3. **Timesheet view:** Go to **Reports → Timesheets** for a weekly grid view. Click any cell to log time.

**Billable Hours (Pro+):**
- Mark time entries as billable or non-billable
- Set hourly rates per user or per project
- Export timesheets as CSV for invoicing

**Time Reports:**
- Filter by project, user, date range, or billable status
- View breakdowns: by day, week, or month
- Export to CSV or PDF

**Known Limitation:** The timer does not run when the browser tab is closed. Use the desktop or mobile app for background tracking.

### File Sharing

**Uploading Files:**
- Drag and drop files directly into a task description or comment
- Click the **attachment icon** on any task
- Maximum file size: 250 MB per file
- Supported preview formats: Images (PNG, JPG, GIF, SVG), PDFs, videos (MP4, MOV up to 100 MB), and text files

**Storage Limits:**
| Plan | Storage |
|------|---------|
| Free | 500 MB |
| Pro | 50 GB |
| Enterprise | Unlimited |

**Google Drive Integration:**
- Link Google Drive files directly to tasks without consuming TaskFlow storage
- Files remain in your Drive; TaskFlow stores a reference link
- Changes in Drive are reflected automatically

### Automations (Pro and Enterprise)

Automations let you create "if this, then that" rules to reduce manual work.

**Creating an Automation:**
1. Go to **Project Settings → Automations**
2. Click **"+ New Automation"**
3. Choose a trigger, condition, and action

**Available Triggers:**
- Task status changes
- Task is created
- Due date arrives
- Task is assigned
- Comment is added
- Label is added/removed

**Available Actions:**
- Change task status
- Assign/unassign a member
- Add a label
- Set priority
- Send a notification (in-app, email, or Slack)
- Move task to another project
- Create a subtask

**Example Automations:**
- "When a task moves to **Done**, notify the project owner via Slack"
- "When a task is created with label **Bug**, set priority to **High** and assign to @priya"
- "When due date is **tomorrow**, send an email reminder to the assignee"

**Limits:** Free plan: 0 automations. Pro: 50 automations per workspace. Enterprise: Unlimited.

### Reporting & Dashboards

**Built-in Reports (Pro+):**
- **Burndown Chart** — Track remaining work over a sprint/time period
- **Velocity Chart** — Tasks completed per week/sprint over time
- **Workload View** — See task distribution across team members, spot overallocation
- **Time Report** — Hours logged by user, project, or date range
- **Status Distribution** — Pie chart of tasks by status across projects

**Custom Dashboards (Enterprise):**
- Create custom dashboards with drag-and-drop widgets
- Share dashboards with team or keep private
- Available widgets: charts, task lists, activity feed, metrics counters, embedded notes

---

## Integrations

### Slack
**Setup:**
1. Go to **Settings → Integrations → Slack**
2. Click **"Connect to Slack"** and authorize TaskFlow in your Slack workspace
3. Choose a default Slack channel for notifications
4. Configure which events trigger Slack messages (task created, status changed, comment added, due date approaching)

**Features:**
- Receive TaskFlow notifications in Slack channels
- Create tasks from Slack using the `/taskflow create` command
- Preview task details with link unfurling — paste a TaskFlow URL in Slack to see a rich preview

**Troubleshooting Slack Integration:**
- If notifications stop working: Go to Settings → Integrations → Slack → click **"Reconnect"**. This re-authorizes the webhook.
- If the `/taskflow` command doesn't work: Ensure the Slack app is installed at the workspace level (not just your personal account). Ask your Slack admin to approve the app.
- Link previews not showing: The person who connected the Slack integration must still be an active member of the TaskFlow workspace.

### Google Drive
**Setup:**
1. Go to **Settings → Integrations → Google Drive**
2. Click **"Connect"** and sign in with your Google account
3. Grant TaskFlow read access to your Drive

**Features:**
- Attach Google Drive files to tasks without uploading
- Browse and search your Drive files from within TaskFlow
- Automatic sync — renamed or moved files in Drive update in TaskFlow

**Troubleshooting Google Drive:**
- "Access denied" error: Re-authorize the connection in Settings → Integrations → Google Drive → Reconnect
- Files not syncing: TaskFlow syncs file metadata every 15 minutes. Click the refresh icon on an attachment to force sync.

### GitHub
**Setup:**
1. Go to **Settings → Integrations → GitHub**
2. Click **"Connect"** and authorize via GitHub OAuth
3. Select which repositories to link

**Features:**
- Link GitHub commits, PRs, and issues to TaskFlow tasks
- Automatic status updates: When a linked PR is merged, the TaskFlow task can auto-move to "Done"
- View GitHub activity in the task activity feed

**Troubleshooting GitHub:**
- Commits not linking: Make sure the commit message includes the TaskFlow task ID in the format `TF-1234`
- Auto-status not working: Check that the automation rule is enabled in Project Settings → Automations
- "Repository not found" error: The GitHub user who connected the integration must have access to the repository

### Google Calendar
**Setup:**
1. Go to **Settings → Integrations → Google Calendar**
2. Authorize TaskFlow to access your calendar
3. Choose sync direction: one-way (TaskFlow → Calendar) or two-way

**Features:**
- TaskFlow tasks with due dates appear as calendar events
- Two-way sync: Rescheduling in Google Calendar updates the TaskFlow due date
- Color-coded by project

### Zapier
**Setup:**
1. Go to **zapier.com** and search for "TaskFlow"
2. Connect your TaskFlow account using an API key (found in Settings → API → Generate Key)
3. Build zaps using TaskFlow as a trigger or action

**Available Triggers:** New task created, task status changed, task completed, new comment
**Available Actions:** Create task, update task, add comment, create project

### Microsoft Teams (Beta)
**Setup:**
1. Settings → Integrations → Microsoft Teams
2. Authorize and select a Teams channel
3. Currently supports notifications only (task creation, status changes)

---

## Account Management

### Billing

**Viewing Your Plan:**
- Go to **Settings → Billing** to see your current plan, billing cycle, and next payment date

**Upgrading:**
1. Go to **Settings → Billing → Change Plan**
2. Select a new plan
3. Upgrades take effect immediately; you're charged a prorated amount for the remainder of your billing cycle

**Downgrading:**
1. Go to **Settings → Billing → Change Plan**
2. Select a lower plan
3. Downgrades take effect at the end of your current billing cycle
4. **Warning:** Downgrading may disable features. If you exceed the new plan's limits (e.g., projects, storage, automations), you'll be prompted to choose which items to archive.

**Payment Methods:**
- Credit card (Visa, Mastercard, American Express)
- Invoiced billing available for Enterprise annual contracts (contact sales@techcorp.io)
- We do not accept PayPal, wire transfer, or cryptocurrency

**Invoices:**
- Monthly invoices are emailed to the workspace admin automatically
- Past invoices are available in Settings → Billing → Invoice History
- Download as PDF for accounting records

**Cancellation:**
1. Go to **Settings → Billing → Cancel Subscription**
2. Complete the cancellation survey (optional)
3. Your workspace remains active until the end of the current billing cycle
4. After cancellation, your workspace moves to the Free plan (data is retained for 90 days, then archived)
5. To reactivate, simply upgrade from the Free plan at any time

**Refund Policy:**
- Full refund within 14 days of initial purchase if you've used the product for less than 7 days
- Prorated refund for annual plans cancelled within the first 30 days
- No refunds after 30 days on annual plans or after 14 days on monthly plans
- Billing disputes should be directed to billing@techcorp.io or escalated through support

### User Roles & Permissions

**Workspace Roles:**
- **Owner** — Full access, can delete workspace, transfer ownership (one per workspace)
- **Admin** — Full access except workspace deletion and ownership transfer
- **Member** — Can create and manage projects and tasks, cannot manage workspace settings or billing
- **Guest** — Limited to specific projects they're invited to, cannot create projects

**Changing a User's Role:**
1. Go to **Settings → Members**
2. Click the role dropdown next to the user's name
3. Select the new role
4. Only Owners and Admins can change roles

**Removing a Member:**
1. Go to **Settings → Members**
2. Click the **"..."** menu next to the user
3. Select **"Remove from Workspace"**
4. Their tasks will remain but will be marked as unassigned
5. Re-invite them anytime; their previous tasks will be re-linked

### Data & Privacy

- **Data location:** All data stored in AWS US-East-1 (Virginia) and AWS EU-West-1 (Ireland) for EU customers
- **Encryption:** AES-256 at rest, TLS 1.3 in transit
- **SOC 2 Type II:** Certified (Enterprise plan)
- **GDPR:** Compliant; Data Processing Agreement (DPA) available on request
- **CCPA:** Compliant
- **Data export:** Settings → Account → Export Data (JSON or CSV, takes up to 24 hours to generate)
- **Account deletion:** Settings → Account → Delete Account. All data is permanently deleted within 30 days. This action cannot be undone.
- **Data retention after cancellation:** Workspace data retained for 90 days on the Free plan, then permanently archived. Contact support within 90 days to restore.

---

## Mobile App

### Supported Platforms
- **iOS:** Requires iOS 15.0 or later (iPhone and iPad)
- **Android:** Requires Android 10 or later

### Key Features
- View and manage tasks, projects, and boards
- Push notifications for assignments, comments, due dates, and mentions
- Built-in time tracker with background running
- Offline mode: View and edit tasks offline; changes sync when you reconnect
- Camera integration: Take a photo and attach it directly to a task

### Known Limitations
- Gantt view is not available on mobile (use tablet or desktop)
- Automation creation/editing is desktop only
- File uploads limited to 50 MB on mobile (vs. 250 MB on desktop)
- Offline mode supports up to 500 tasks; larger projects may not fully cache

### Push Notification Settings
1. Open the TaskFlow mobile app
2. Go to **Settings → Notifications**
3. Toggle notifications for: assignments, comments, mentions, due date reminders, status changes
4. Set quiet hours to silence notifications during specific times
5. **Note:** Push notifications also require notifications to be enabled at the OS level (iOS Settings → TaskFlow → Notifications, or Android Settings → Apps → TaskFlow → Notifications)

---

## Troubleshooting

### Login Problems

**"Invalid credentials" error:**
1. Verify you're using the correct email address (the one you signed up with)
2. Check for typos and ensure Caps Lock is off
3. Try resetting your password: Click **"Forgot Password?"** on the login page
4. Password reset emails are sent within 2 minutes. Check your spam/junk folder.
5. If you signed up via Google SSO, click **"Sign in with Google"** instead of entering a password

**"Account not found" error:**
- You may have signed up with a different email. Try other email addresses you use.
- If your workspace was on a Free plan and was inactive for 180+ days, it may have been archived. Contact support to restore.

**"Too many login attempts" lockout:**
- After 5 failed attempts, your account is locked for 30 minutes
- Wait 30 minutes and try again, or reset your password immediately via the email link

**Two-Factor Authentication (2FA) issues:**
- If you lost your 2FA device, use one of your backup recovery codes (provided when you enabled 2FA)
- If you've lost your recovery codes, contact support with your account email and ID verification

### Sync Issues

**Tasks not updating in real-time:**
1. Check your internet connection
2. Refresh the page (Ctrl/Cmd + R)
3. Clear browser cache: Settings → Privacy → Clear Browsing Data → Cached Images and Files
4. Try a different browser (TaskFlow supports Chrome, Firefox, Safari, Edge — latest 2 versions)
5. Check TaskFlow status at **status.taskflow.io** for any ongoing incidents

**Mobile app not syncing:**
1. Ensure you're connected to the internet (Wi-Fi or cellular)
2. Pull down on the main screen to force a refresh
3. Go to App Settings → Sync → "Force Full Sync"
4. If still not working: log out, clear app cache, and log back in
5. Ensure you have the latest app version installed

**Integration sync delays:**
- Slack notifications: Typically instant, but may delay up to 60 seconds during high load
- Google Drive: Metadata syncs every 15 minutes; force sync with the refresh icon
- GitHub: Webhook-based, should be near-instant. If delayed, check the webhook status in GitHub Settings → Webhooks
- Google Calendar: Two-way sync runs every 10 minutes

### Notification Settings

**Not receiving email notifications:**
1. Check Settings → Notifications → Email and ensure the relevant toggles are on
2. Check your spam/junk folder and add noreply@taskflow.io to your contacts
3. Verify your email address in Settings → Profile → Email (click "Resend Verification" if needed)
4. Email notifications are batched — if you have "Batch notifications" enabled, you'll receive a digest instead of individual emails

**Not receiving push notifications on mobile:**
1. In the TaskFlow app: Settings → Notifications → ensure toggles are on
2. In your phone's settings: ensure notifications are enabled for TaskFlow
3. On iOS: Check Settings → TaskFlow → Notifications → Allow Notifications
4. On Android: Check Settings → Apps → TaskFlow → Notifications → Show Notifications
5. Ensure you're not in Do Not Disturb or Focus mode
6. Try uninstalling and reinstalling the app

**Too many notifications:**
1. Go to Settings → Notifications
2. Disable notification types you don't need
3. Enable "Batch notifications" to receive a daily or hourly digest instead
4. Set Quiet Hours in the mobile app to pause notifications during off hours
5. You can mute individual projects: Right-click the project → "Mute Notifications"

### Mobile App Problems

**App crashes on startup:**
1. Force close the app and reopen it
2. Ensure your device OS is up to date
3. Update the TaskFlow app to the latest version
4. Clear the app cache (device Settings → Apps → TaskFlow → Clear Cache)
5. If the issue persists, uninstall and reinstall the app (your data is stored in the cloud and won't be lost)

**"Session expired" error on mobile:**
- This occurs when your login session has timed out (sessions expire after 30 days of inactivity)
- Simply log in again with your credentials or SSO

**Offline mode not working:**
- Offline mode must be enabled in App Settings → Offline → "Enable Offline Access"
- The initial offline cache takes a few minutes to build after enabling
- Only the 500 most recent tasks are cached offline
- Offline changes sync automatically when connectivity is restored

### Performance Issues

**TaskFlow running slowly:**
1. Close unnecessary browser tabs (TaskFlow performs best with fewer than 50 open tabs total)
2. Disable browser extensions that may interfere (ad blockers, privacy extensions)
3. Try Incognito/Private mode to rule out extension conflicts
4. Clear browser cache and cookies for taskflow.io
5. Check your internet speed — TaskFlow requires at least 5 Mbps for optimal performance
6. If a specific project is slow, it may have too many tasks in a single view. Use filters to narrow down the displayed tasks.

**Dashboard loading slowly:**
- Dashboards with many widgets or large date ranges may take longer to load
- Try reducing the date range or removing widgets you don't actively use
- Enterprise dashboards with 10+ widgets may take up to 10 seconds to load — this is expected

---

## Frequently Asked Questions

### General

**Q1: What is TaskFlow?**
A: TaskFlow is a cloud-based project management platform designed for small and medium businesses. It helps teams organize work with tasks, project boards, time tracking, collaboration tools, and reporting — all in one place.

**Q2: Is there a free plan?**
A: Yes! Our Free plan includes up to 5 users, 3 projects, 500 MB storage, and access to Board and List views. No credit card required to sign up.

**Q3: Can I try Pro features before committing?**
A: Absolutely. We offer a **14-day free trial** of the Pro plan. No credit card required. If you don't upgrade after the trial, your workspace automatically moves to the Free plan.

**Q4: What browsers does TaskFlow support?**
A: TaskFlow supports the latest two versions of Chrome, Firefox, Safari, and Microsoft Edge. We recommend Chrome for the best experience.

**Q5: Is there a desktop app?**
A: Not currently. TaskFlow is a web application accessible from any browser. We also have mobile apps for iOS and Android. A desktop app is on our roadmap for later this year.

**Q6: Can I import data from other project management tools?**
A: Yes! We support direct import from Trello, Asana, Jira, and Monday.com. Go to Settings → Import Data and follow the wizard. CSV import is also available for other tools.

**Q7: Does TaskFlow work offline?**
A: The mobile app supports offline mode for viewing and editing up to 500 tasks. Changes sync automatically when you reconnect. The web app requires an internet connection.

### Account & Access

**Q8: How do I reset my password?**
A: Click "Forgot Password?" on the login page at app.taskflow.io. Enter your email and follow the link sent to your inbox. The reset link expires after 24 hours.

**Q9: How do I enable two-factor authentication (2FA)?**
A: Go to Settings → Security → Two-Factor Authentication → Enable. You can use any TOTP authenticator app (Google Authenticator, Authy, 1Password). Save your backup recovery codes in a safe place.

**Q10: Can I change my workspace name?**
A: Yes. Go to Settings → Workspace → Workspace Name. Only workspace Owners and Admins can change the name.

**Q11: How do I transfer workspace ownership?**
A: Go to Settings → Workspace → Transfer Ownership. Enter the email of the new owner (they must be an existing workspace Admin). This action requires email confirmation from both parties.

**Q12: How do I delete my account?**
A: Go to Settings → Account → Delete Account. This permanently deletes your account and all associated data within 30 days. If you're the workspace Owner, you must transfer ownership first. This action cannot be undone.

### Billing & Pricing

**Q13: When am I charged?**
A: Monthly plans are charged on the same date each month (your signup date). Annual plans are charged once per year upfront.

**Q14: What happens if my payment fails?**
A: We'll retry the charge 3 times over 7 days and send email notifications each time. If all retries fail, your workspace is downgraded to the Free plan after 14 days. Your data is preserved — upgrade anytime to restore access.

**Q15: Do you offer discounts for nonprofits or education?**
A: Yes! We offer 50% off Pro and Enterprise plans for verified nonprofit organizations and educational institutions. Contact sales@techcorp.io with proof of status.

**Q16: Can I get a refund?**
A: We offer a full refund within 14 days of your initial purchase if you've used the product for less than 7 days. Annual plan customers can receive a prorated refund within 30 days. Contact billing@techcorp.io for refund requests.

**Q17: How do I change my payment method?**
A: Go to Settings → Billing → Payment Method → Update. Enter your new card details. The change takes effect immediately and applies to your next billing cycle.

### Features & Usage

**Q18: What's the difference between Board view and List view?**
A: Board view displays tasks as cards in columns (Kanban style) — great for visual workflows. List view shows tasks in a table format with sortable columns — better for detailed data and bulk editing. Both show the same tasks; it's just a different way of looking at them.

**Q19: How do I set up automations?**
A: Go to Project Settings → Automations → "+ New Automation". Choose a trigger (e.g., "task status changes to Done"), set conditions (optional), and pick an action (e.g., "send Slack notification"). Automations are available on Pro and Enterprise plans.

**Q20: Can I create recurring tasks?**
A: Yes! When editing a task, click the **calendar icon** next to the due date and select **"Repeat"**. Choose daily, weekly, monthly, or custom recurrence. When you complete a recurring task, a new instance is automatically created with the next due date.

**Q21: How many integrations can I connect?**
A: Free plan: 1 integration. Pro plan: Unlimited integrations. Enterprise plan: Unlimited integrations plus API access.

**Q22: Can I export my data?**
A: Yes. Go to Settings → Account → Export Data. Choose JSON or CSV format. The export includes all projects, tasks, comments, time entries, and attachments metadata. Export generation takes up to 24 hours; you'll receive an email with a download link.

**Q23: What is the API rate limit?**
A: The TaskFlow API allows 100 requests per minute per user on Pro plans and 500 requests per minute on Enterprise plans. If you exceed the limit, you'll receive a 429 (Too Many Requests) response. API access is not available on the Free plan.

**Q24: Can guests use time tracking?**
A: No. Guests have limited access and cannot use time tracking. They can view and comment on tasks in projects they're invited to, but time tracking requires a Member or Admin role.

**Q25: How do I archive a project?**
A: Open the project → click the **"..."** menu in the top right → select **"Archive Project"**. Archived projects are hidden from the sidebar but can be found in Settings → Projects → Archived. You can restore an archived project at any time.

### Technical

**Q26: Is my data backed up?**
A: Yes. We perform automated backups every 6 hours. Backups are stored in geographically redundant locations and retained for 30 days. Enterprise customers can request point-in-time recovery within 30 days by contacting support.

**Q27: What uptime SLA does TaskFlow offer?**
A: Enterprise plans include a 99.9% uptime SLA. Pro and Free plans target the same uptime but without a contractual guarantee. Check real-time status at status.taskflow.io.

**Q28: Does TaskFlow support Single Sign-On (SSO)?**
A: SSO via SAML 2.0 is available on the Enterprise plan. We support Okta, Azure AD, Google Workspace, and OneLogin. Go to Settings → Security → SSO to configure.

**Q29: Can I use TaskFlow with a VPN?**
A: Yes. TaskFlow is a standard web application and works behind most VPNs. If you experience connection issues, ensure your VPN allows traffic to *.taskflow.io and *.amazonaws.com.

**Q30: What happens to my data if I cancel?**
A: Your workspace moves to the Free plan. If your usage exceeds Free plan limits, you'll be prompted to archive items. Data is retained for 90 days on the Free plan after cancellation. After 90 days, inactive workspaces are permanently archived. Contact support within 90 days to export or restore your data.
