"""
Utility functions for bills management
Handles recurring bills and budget tracking
"""
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from database import get_db_connection

logger = logging.getLogger(__name__)

def process_recurring_bills():
    """
    Process recurring bills - create next month's bills when current ones are paid
    Should be run periodically (e.g., daily via cron or on app startup)
    """
    conn = get_db_connection()
    
    try:
        # Get all recurring bills that are paid and need renewal
        bills = conn.execute('''
            SELECT * FROM bills 
            WHERE is_recurring = TRUE 
            AND is_paid = TRUE
            AND paid_date IS NOT NULL
        ''').fetchall()
        
        for bill in bills:
            # Check if we need to create next period's bill
            if should_create_next_bill(bill):
                create_next_recurring_bill(conn, bill)
        
        conn.commit()
        logger.info(f"Processed {len(bills)} recurring bills")
        
    except Exception as e:
        logger.error(f"Error processing recurring bills: {e}")
        conn.rollback()
    finally:
        conn.close()

def should_create_next_bill(bill):
    """Check if next bill period should be created"""
    if not bill['paid_date']:
        return False
    
    paid_date = datetime.strptime(bill['paid_date'], '%Y-%m-%d').date()
    today = datetime.now().date()
    pattern = bill['recurrence_pattern']
    
    if pattern == 'monthly':
        next_due = paid_date + relativedelta(months=1)
    elif pattern == 'weekly':
        next_due = paid_date + timedelta(weeks=1)
    elif pattern == 'yearly':
        next_due = paid_date + relativedelta(years=1)
    else:
        return False
    
    # Create next bill if we're within 5 days of the next due date
    return (next_due - today).days <= 5

def create_next_recurring_bill(conn, original_bill):
    """Create the next period's bill based on recurring pattern"""
    try:
        # Check if next bill already exists (avoid duplicates)
        existing = conn.execute('''
            SELECT id FROM bills 
            WHERE bill_name = ? 
            AND added_by = ?
            AND is_paid = FALSE
            AND category = ?
        ''', (original_bill['bill_name'], original_bill['added_by'], original_bill['category'])).fetchone()
        
        if existing:
            logger.info(f"Next bill for {original_bill['bill_name']} already exists")
            return
        
        # Create new unpaid bill for next period
        conn.execute('''
            INSERT INTO bills (
                bill_name, amount, due_day, category, 
                is_recurring, recurrence_pattern, is_paid, added_by
            ) VALUES (?, ?, ?, ?, ?, ?, FALSE, ?)
        ''', (
            original_bill['bill_name'],
            original_bill['amount'],
            original_bill['due_day'],
            original_bill['category'],
            original_bill['is_recurring'],
            original_bill['recurrence_pattern'],
            original_bill['added_by']
        ))
        
        logger.info(f"Created next recurring bill: {original_bill['bill_name']}")
        
    except Exception as e:
        logger.error(f"Error creating next recurring bill: {e}")
        raise

def mark_bill_paid(bill_id, user_id, payment_date=None):
    """Mark a bill as paid and record payment history"""
    conn = get_db_connection()
    
    try:
        if payment_date is None:
            payment_date = datetime.now().date().isoformat()
        
        # Get bill details
        bill = conn.execute('SELECT * FROM bills WHERE id = ?', (bill_id,)).fetchone()
        
        if not bill:
            return False
        
        # Mark bill as paid
        conn.execute('''
            UPDATE bills 
            SET is_paid = TRUE, paid_date = ?, paid_by = ?
            WHERE id = ?
        ''', (payment_date, user_id, bill_id))
        
        # Record payment in history
        conn.execute('''
            INSERT INTO bill_payments (bill_id, amount, payment_date, paid_by)
            VALUES (?, ?, ?, ?)
        ''', (bill_id, bill['amount'], payment_date, user_id))
        
        conn.commit()
        
        # If recurring, check if we should create next bill immediately
        if bill['is_recurring'] and should_create_next_bill(bill):
            create_next_recurring_bill(conn, bill)
            conn.commit()
        
        logger.info(f"Bill {bill_id} marked as paid by user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error marking bill as paid: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_budget_analytics(year=None, month=None):
    """Get budget analytics for specified period"""
    conn = get_db_connection()
    
    if year is None:
        year = datetime.now().year
    if month is None:
        month = datetime.now().month
    
    try:
        # Get spending by category for the month
        spending = conn.execute('''
            SELECT 
                category,
                SUM(amount) as total_spent,
                COUNT(*) as bill_count
            FROM bills
            WHERE is_paid = TRUE
            AND strftime('%Y', paid_date) = ?
            AND strftime('%m', paid_date) = ?
            GROUP BY category
        ''', (str(year), f"{month:02d}")).fetchall()
        
        # Get budget limits
        categories = conn.execute('SELECT * FROM budget_categories').fetchall()
        
        # Combine data
        analytics = []
        total_spent = 0
        total_budget = 0
        
        for cat in categories:
            spent = next((s['total_spent'] for s in spending if s['category'] == cat['name']), 0)
            limit = cat['monthly_limit'] or 0
            
            analytics.append({
                'category': cat['name'],
                'spent': float(spent),
                'limit': float(limit),
                'color': cat['color'],
                'percentage': (spent / limit * 100) if limit > 0 else 0,
                'over_budget': spent > limit if limit > 0 else False
            })
            
            total_spent += float(spent)
            total_budget += float(limit)
        
        return {
            'analytics': analytics,
            'total_spent': total_spent,
            'total_budget': total_budget,
            'period': f"{year}-{month:02d}"
        }
        
    except Exception as e:
        logger.error(f"Error getting budget analytics: {e}")
        return None
    finally:
        conn.close()

def get_spending_history(months=6):
    """Get spending history for the last N months"""
    conn = get_db_connection()
    
    try:
        history = []
        today = datetime.now()
        
        for i in range(months):
            date = today - relativedelta(months=i)
            year = date.year
            month = date.month
            
            total = conn.execute('''
                SELECT SUM(amount) as total
                FROM bills
                WHERE is_paid = TRUE
                AND strftime('%Y', paid_date) = ?
                AND strftime('%m', paid_date) = ?
            ''', (str(year), f"{month:02d}")).fetchone()
            
            history.append({
                'month': date.strftime('%b %Y'),
                'total': float(total['total'] or 0)
            })
        
        return list(reversed(history))
        
    except Exception as e:
        logger.error(f"Error getting spending history: {e}")
        return []
    finally:
        conn.close()
