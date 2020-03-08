from django.db import models
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
# from django.contrib.govinterface.models import LogEntry
from polymorphic.models import PolymorphicModel
from django.core.exceptions import ValidationError
from policyengine.views import execute_action, check_policy_code, check_filter_code, initialize_code
import urllib
import json

import logging


logger = logging.getLogger(__name__)



class CommunityIntegration(PolymorphicModel):
    community_name = models.CharField('team_name', 
                              max_length=1000)
    
    user_group = models.ForeignKey(Group, models.CASCADE)


class CommunityUser(User, PolymorphicModel):
        
    readable_name = models.CharField('readable_name', 
                                      max_length=300, null=True)
    
    community_integration = models.ForeignKey(CommunityIntegration,
                                   models.CASCADE)
    
        
    access_token = models.CharField('access_token', 
                                     max_length=300, null=True)
    
    is_community_admin = models.BooleanField(default=False)
    
        
    def save(self, *args, **kwargs):      
        super(User, self).save(*args, **kwargs)
        p1 = Permission.objects.get(name='Can add processpolicy')
        p2 = Permission.objects.get(name='Can add communitypolicy')
        self.user_permissions.add(p1)
        self.user_permissions.add(p2)
        
        p3 = Permission.objects.get(name='Can add user vote')
        p4 = Permission.objects.get(name='Can change user vote')
        p5 = Permission.objects.get(name='Can delete user vote')
        p6 = Permission.objects.get(name='Can view user vote')
        self.user_permissions.add(p3)
        self.user_permissions.add(p4)
        self.user_permissions.add(p5)
        self.user_permissions.add(p6)
        
        p7 = Permission.objects.get(name='Can add communityactionbundle')
        self.user_permissions.add(p7)
        
    def __str__(self):
        return self.readable_name + '@' + self.community_integration.community_name
        
        
        
class DataStore(models.Model):
    
    data_store = models.TextField()
        
    def _get_data_store(self):
        if self.data_store != '':
            return json.loads(self.data_store)
        else:
            return {}
    
    def _set_data_store(self, obj):
        self.data_store = json.dumps(obj)
        self.save()
    
    def get_item(self, key):
        obj = self._get_data_store()
        return obj.get(key, None)
    
    def add_or_update_item(self, key, value):
        obj = self._get_data_store()
        obj[key] = value
        self._set_data_store(obj)
        return True
    
    def delete_item(self, key):
        obj = self._get_data_store()
        res = obj.pop(key, None)
        self._set_data_store(obj)
        if not res:
            return False
        return True

        
class LogAPICall(models.Model):
    community_integration = models.ForeignKey(CommunityIntegration,
                                   models.CASCADE)
    proposal_time = models.DateTimeField(auto_now_add=True)
    call_type = models.CharField('call_type', max_length=300)
    extra_info = models.TextField()
    
    @classmethod
    def make_api_call(cls, community_integration, values, call):
        logger.info("COMMUNITY API CALL")
        logger.info(call)
             
        _ = LogAPICall.objects.create(community_integration = community_integration,
                                      call_type = call,
                                      extra_info = json.dumps(values)
                                      )
        
        data = urllib.parse.urlencode(values)   
        data = data.encode('utf-8')
        logger.info(data)
        
        call_info = call + '?'
        req = urllib.request.Request(call_info, data)
        resp = urllib.request.urlopen(req)
        res = json.loads(resp.read().decode('utf-8'))
        logger.info("COMMUNITY API RESPONSE")
        logger.info(res)
        return res
        
        
class CommunityAPI(PolymorphicModel):
    ACTION = None
    AUTH = 'app'
    
    community_integration = models.ForeignKey(CommunityIntegration,
                                   models.CASCADE)
    
    initiator = models.ForeignKey(CommunityUser,
                                models.CASCADE)
    
    community_post = models.CharField('community_post', 
                                         max_length=300, null=True)
    
    community_revert = models.BooleanField(default=False)
    
    community_origin = models.BooleanField(default=False)
    
    is_bundled = models.BooleanField(default=False)
    
    def revert(self, values, call):
        _ = LogAPICall.make_api_call(self.community_integration, values, call)
        self.community_revert = True
        self.save()
        
    def post_policy(self, policy, post_type='channel', users=None, template=None, channel=None):
        values = {'token': self.community_integration.access_token}
        
        if not template:
            policy_message = "This action is governed by the following policy: " + policy.explanation + '. Vote with :thumbsup: or :thumbsdown: on this post.'
        else:
            policy_message = template

        values['text'] = policy_message
        
        # mpim - all users
        # im each user
        # channel all users
        # channel ephemeral users
        
        if post_type == "mpim":
            api_call = 'chat.postMessage'
            user_ids = [user.username for user in users]
            info = {'token': self.community_integration.access_token}
            info['users'] = ','.join(user_ids)
            call = self.community_integration.API + 'conversations.open'
            res = LogAPICall.make_api_call(self.community_integration, info, call)
            channel = res['channel']['id']
            values['channel'] = channel
            
            call = self.community_integration.API + api_call
            res = LogAPICall.make_api_call(self.community_integration, values, call)
            self.community_post = res['ts']
            self.save()
        elif post_type == 'im':
            api_call = 'chat.postMessage'
            user_ids = [user.username for user in users]
            
            for user_id in user_ids:
                info = {'token': self.community_integration.access_token}
                info['users'] = user_id
                call = self.community_integration.API + 'conversations.open'
                res = LogAPICall.make_api_call(self.community_integration, info, call)
                channel = res['channel']['id']
                values['channel'] = channel
                
                call = self.community_integration.API + api_call
                res = LogAPICall.make_api_call(self.community_integration, values, call)
                self.community_post = res['ts']
                self.save()
        elif post_type == 'ephemeral':
            api_call = 'chat.postEphemeral'
            user_ids = [user.username for user in users]
            
            for user_id in user_ids:
                values['user'] = user_id
                values['channel'] = self.channel
                call = self.community_integration.API + api_call
                res = LogAPICall.make_api_call(self.community_integration, values, call)
                self.community_post = res['ts']
                self.save()
        elif post_type == 'channel':
            api_call = 'chat.postMessage'
            if channel:
                values['channel'] = channel
            else:
                values['channel'] = self.channel
            call = self.community_integration.API + api_call
            res = LogAPICall.make_api_call(self.community_integration, values, call)
            self.community_post = res['ts']
            self.save()
        
            
    def save(self, *args, **kwargs):
        logger.info(self.community_post)
        
        if not self.pk:
            # Runs only when object is new
            super(CommunityAPI, self).save(*args, **kwargs)
            
            if not self.is_bundled:
                _ = CommunityAction.objects.create(community_integration=self.community_integration,
                                                   api_action=self
                                                  )
        else:
            super(CommunityAPI, self).save(*args, **kwargs) 
        
        
class Proposal(models.Model):
    
    author = models.ForeignKey(
        CommunityUser,
        models.CASCADE,
        verbose_name='author', 
        blank=True
        )
    
    proposal_time = models.DateTimeField(auto_now_add=True)
    
    PROPOSED = 'proposed'
    FAILED = 'failed'
    PASSED = 'passed'
    
    STATUS = [
            (PROPOSED, 'proposed'),
            (FAILED, 'failed'),
            (PASSED, 'passed')
        ]
    
    status = models.CharField(choices=STATUS, max_length=10)
    
    data = models.OneToOneField(DataStore, 
        models.CASCADE,
        verbose_name='data',
        null=True
    )
    
    def save(self, *args, **kwargs):
        if not self.pk:
            ds = DataStore.objects.create()
            self.data = ds
        
        super(Proposal, self).save(*args, **kwargs)
            

       
class BaseAction(models.Model):
    community_integration = models.ForeignKey(CommunityIntegration, 
        models.CASCADE,
        verbose_name='community_integration',
    )
    
    proposal = models.OneToOneField(Proposal,
                                 models.CASCADE)
    
    class Meta:
        abstract = True   

    def save(self, *args, **kwargs):
        if not self.pk:
            super(BaseAction, self).save(*args, **kwargs)
            
            action = self
            for policy in CommunityPolicy.objects.filter(proposal__status=Proposal.PASSED, community_integration=self.community_integration):
                if check_filter_code(policy, action):
                    
                    initialize_code(policy, action)
                    
                    cond_result = check_policy_code(policy, action)
                    if cond_result == Proposal.PASSED:
                        exec(policy.policy_action_code)
                    elif cond_result == Proposal.FAILED:
                        exec(policy.policy_failure_code)
                    else:
                        exec(policy.policy_notify_code)
        else:
            super(BaseAction, self).save(*args, **kwargs)      
        



class ProcessAction(BaseAction):
     
    content_type = models.ForeignKey(
        ContentType,
        models.CASCADE,
        verbose_name='content type',
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    class Meta:
        verbose_name = 'processaction'
        verbose_name_plural = 'processactions'


class CommunityAction(BaseAction):
    
    api_action = models.OneToOneField(CommunityAPI,
                                      models.CASCADE)
    
    class Meta:
        verbose_name = 'communityaction'
        verbose_name_plural = 'communityactions'

    def __str__(self):
        return ' '.join(['Action: ', str(self.api_action), 'to', self.community_integration.community_name])

    def save(self, *args, **kwargs):
        if not self.pk:
            # Runs only when object is new
            p = Proposal.objects.create(status=Proposal.PROPOSED,
                                        author=self.api_action.initiator)
            
            self.proposal = p
            
            super(CommunityAction, self).save(*args, **kwargs)

        else:   
            super(CommunityAction, self).save(*args, **kwargs)
        

  
class CommunityActionBundle(BaseAction):
      
    bundled_api_actions = models.ManyToManyField(CommunityAPI)

    class Meta:
        verbose_name = 'communityactionbundle'
        verbose_name_plural = 'communityactionbundles'

    def save(self, *args, **kwargs):
        if not self.pk:
            # Runs only when object is new
            p = Proposal.objects.create(status=Proposal.PROPOSED,
                                        author=self.bundled_api_actions.al()[0].initiator)
            
            self.proposal = p
            super(CommunityAction, self).save(*args, **kwargs)
        else:   
            super(CommunityAction, self).save(*args, **kwargs)
            
    

class BasePolicy(models.Model):
    community_integration = models.ForeignKey(CommunityIntegration, 
        models.CASCADE,
        verbose_name='community_integration',
    )
    
    proposal = models.OneToOneField(Proposal,
                                 models.CASCADE)
    
    explanation = models.TextField(null=True, blank=True)
    
    class Meta:
        abstract = True
    
    
class ProcessPolicy(BasePolicy):    
    policy_code = models.TextField()
    
    class Meta:
        verbose_name = 'processpolicy'
        verbose_name_plural = 'processpolicies'

        
    def __str__(self):
        return ' '.join(['ProcessPolicy: ', self.explanation, 'for', self.community_integration.community_name])
    
    
    
class CommunityPolicy(BasePolicy):
    policy_filter_code = models.TextField(blank=True, default='')
    policy_init_code = models.TextField(blank=True, default='')
    policy_notify_code = models.TextField(blank=True, default='')
    policy_conditional_code = models.TextField(blank=True, default='')
    policy_action_code = models.TextField(blank=True, default='')
    policy_failure_code = models.TextField(blank=True, default='')
    
    policy_text = models.TextField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'communitypolicy'
        verbose_name_plural = 'communitypolicies'
        
#     def clean(self):
#         super().clean()
#         if self.policy_action_code is None and self.policy_text is None:
#             raise ValidationError('Code or text rule instructions are both None')

        
    def __str__(self):
        return ' '.join(['CommunityPolicy: ', self.explanation, 'for', self.community_integration.community_name])
    
    def save(self, *args, **kwargs):
        if not self.pk:
            # Runs only when object is new
            process = ProcessPolicy.objects.filter(proposal__status=Proposal.PASSED, community_integration=self.community_integration)
            p = self.proposal
            p.status = Proposal.PROPOSED
            p.save()
            
            super(CommunityPolicy, self).save(*args, **kwargs)
            
            if process.exists():
                policy = self
                exec(process[0].policy_code)

        else:   
            super(CommunityPolicy, self).save(*args, **kwargs)
    

# class VoteSystem(models.Model):
#     
#     class Meta:
#         abstract = True  


class UserVote(models.Model):
    
    user = models.ForeignKey(CommunityUser,
                              models.CASCADE)
    
    proposal = models.ForeignKey(Proposal,
                                models.CASCADE)
    
    boolean_value = models.BooleanField(null=True) # yes/no, selected/not selected
    
    